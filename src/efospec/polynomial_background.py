"""Experimental local background interpolation and covariance-aware boxcar extraction.

Fit detector rows independently. This is a sky+host continuum interpolation,
not a galaxy decomposition or a rectified wavelength-space sky-line model.
"""
import json
from pathlib import Path
import shutil
import numpy as np
from astropy.io import fits

from .inventory import sha256
from .recipes import validate_recipe
from .revisions import FailedExposure
from .native_calibration import save_json


def fit_background(data, variance, trace, *, x_origin, radius, regions, exclude=(),
                   degree=2, sigma_clip=4., good=None):
    data=np.asarray(data,dtype=float);variance=np.asarray(variance,dtype=float)
    trace=np.asarray(trace,dtype=float)
    if (data.ndim!=2 or variance.shape!=data.shape or trace.shape!=(data.shape[0],)
            or not np.isfinite(trace).all() or not np.isfinite(radius) or radius<=0
            or type(degree) is not int or not 0<=degree<=3 or not 3<=sigma_clip<=8):
        raise ValueError('invalid polynomial background arrays or parameters')
    ny,nx=data.shape;x=np.arange(nx,dtype=float)+x_origin
    selected=np.zeros(nx,dtype=bool)
    for lo,hi in regions:selected|=(x>=lo)&(x<hi)
    for lo,hi in exclude:selected&=~((x>=lo)&(x<hi))
    selected[[0,-1]]=False
    if selected.sum()<10:raise ValueError('insufficient requested background samples')
    center=float(np.mean(x[selected]));scale=float(np.ptp(x[selected])/2)
    design=np.polynomial.legendre.legvander((x-center)/scale,degree)
    usable=np.isfinite(data)&np.isfinite(variance)&(variance>0)
    if good is not None:
        if np.shape(good)!=data.shape:raise ValueError('background mask geometry mismatch')
        usable&=good
    weights=np.maximum(0.,np.minimum(x[None,:]+.5,trace[:,None]+radius)
                       -np.maximum(x[None,:]-.5,trace[:,None]-radius))
    requested=selected[None,:]&usable&(weights==0)
    used=np.zeros_like(requested);model=np.full_like(data,np.nan)
    model_variance=np.full_like(data,np.nan)
    coefficients=np.full((ny,degree+1),np.nan);covariance=np.full((ny,degree+1,degree+1),np.nan)
    counts=np.full(ny,np.nan);count_variance=np.full(ny,np.nan);background_counts=np.full(ny,np.nan)
    reduced_chi2=np.full(ny,np.nan);valid=np.zeros(ny,dtype=bool)
    for row in range(ny):
        keep=requested[row].copy()
        if np.any((weights[row]>0)&~usable[row]) or not np.isclose(weights[row].sum(),2*radius):continue
        for iteration in range(10):
            if min(np.sum(keep&(x<trace[row])),np.sum(keep&(x>trace[row])))<5:break
            a=design[keep];invvar=1/variance[row,keep]
            normal=a.T@(invvar[:,None]*a)
            if np.linalg.cond(normal)>1e8:break
            cov=np.linalg.inv(normal);beta=cov@(a.T@(invvar*data[row,keep]))
            prediction=design@beta
            resid=(data[row]-prediction)/np.sqrt(variance[row])
            revised=keep.copy()
            worst=np.flatnonzero(keep)[np.argmax(abs(resid[keep]))]
            if abs(resid[worst])>sigma_clip:revised[worst]=False
            if np.array_equal(revised,keep):
                # Background fit and aperture samples are disjoint. The sum of
                # predicted pixels uses the full coefficient covariance, not
                # a sum of marginal background variances.
                aperture_design=weights[row]@design
                bg=float(aperture_design@beta)
                noise=float(np.sum(weights[row]**2*np.where(usable[row],variance[row],0.)))
                bgvar=float(aperture_design@cov@aperture_design)
                counts[row]=float(weights[row]@np.where(usable[row],data[row],0.)-bg)
                count_variance[row]=noise+bgvar;background_counts[row]=bg
                model[row]=prediction;model_variance[row]=np.einsum('ij,jk,ik->i',design,cov,design)
                coefficients[row]=beta;covariance[row]=cov;used[row]=keep;valid[row]=True
                reduced_chi2[row]=float(np.sum(resid[keep]**2)/(keep.sum()-degree-1))
                break
            keep=revised
    return dict(model=model,model_variance=model_variance,coefficients=coefficients,
        coefficient_covariance=covariance,fit_mask=used,requested_mask=requested,
        aperture_weights=weights,trace_raw=trace,counts=counts,variance=count_variance,
        background_counts=background_counts,valid=valid,reduced_chi2=reduced_chi2,
        basis_center=np.array(center),basis_scale=np.array(scale))


def calculate(exposure, recipe):
    recipe=validate_recipe(recipe,exposure.window,exposure.hashes)
    if recipe['sky']['mode']!='polynomial':raise ValueError('a polynomial background recipe is required')
    obj=recipe['objects'][0];row=int(obj['spec']-exposure.window.origin[0])
    traces=exposure.images['found_traces']+exposure.window.origin[1]
    seed=traces[np.argmin(abs(traces[:,row]-obj['spat']))].copy()
    seed+=obj['spat']-seed[row]
    data=exposure.context.data;h=exposure.frame['metadata']
    variance=np.maximum(data,0.)+float(h['ESO DET OUT1 RON'])**2
    detector=exposure.context.detector
    saturated=data>=float(detector['saturation'])*float(detector['gain'][0])
    result=fit_background(data,variance,seed,x_origin=exposure.window.origin[1],radius=obj['radius'],
        regions=recipe['sky']['include'],exclude=recipe['sky']['exclude'],degree=recipe['sky']['degree'],
        sigma_clip=recipe['sky']['sigma_clip'],good=~saturated)
    x=np.arange(data.shape[1])+exposure.window.origin[1]
    result['wave_air']=np.array([np.interp(t,x,w) for t,w in zip(seed,exposure.context.waveair)])
    lines=np.asarray(exposure.context.arc_qa['reference_lines'])+exposure.context.shift
    result['spectrum_valid']=result['valid']&(result['wave_air']>=lines.min())&(result['wave_air']<=lines.max())
    return recipe,result


def extract_background(run, raw_name, recipe, output, reference_root=None):
    exposure=FailedExposure(run,raw_name,reference_root)
    recipe,result=calculate(exposure,recipe)
    if not result['valid'].any():raise ValueError('no rows have a valid two-sided polynomial background')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    save_json(output/'recipe.json',recipe)
    np.savez_compressed(output/'background-model.npz',**result)
    columns=[fits.Column(name=name,format=fmt,unit=unit,array=values) for name,fmt,unit,values in [
        ('WAVE_AIR','D','Angstrom',result['wave_air']),('COUNTS','D','electron',result['counts']),
        ('SIGMA','D','electron',np.sqrt(result['variance'])),('BACKGROUND','D','electron',result['background_counts']),
        ('VALID','L',None,result['spectrum_valid'])]]
    header=fits.Header({'OBJECT':exposure.result['object'],'EPSTATUS':'EXPERIMENTAL',
        'IDENTITY':'UNVERIFIED','METHOD':'POLY-BOXCAR','WAVEMED':'air','BUNIT':'electron',
        'FLUXCAL':'NONE','BGDEG':recipe['sky']['degree'],'RAWFILE':raw_name})
    fits.HDUList([fits.PrimaryHDU(header=header),fits.BinTableHDU.from_columns(columns,name='SPECTRUM')]).writeto(output/'boxcar-background.fits',checksum=True)
    source=output/'source';source.mkdir()
    for p in Path(__file__).parent.glob('*.py'):shutil.copyfile(p,source/p.name)
    trace=FailedExposure(run,raw_name,reference_root)
    if trace.hashes!=exposure.hashes:raise ValueError('inputs changed during polynomial extraction')
    qa={'status':'EXPERIMENTAL','method':'row_polynomial_background_and_boxcar','target_identity':'UNVERIFIED',
        'raw':exposure.frame['path'],'parent_run':str(exposure.run),'input_sha256':exposure.hashes,
        'recipe_sha256':sha256(output/'recipe.json'),'valid_fraction':float(result['valid'].mean()),
        'valid_spectrum_fraction':float(result['spectrum_valid'].mean()),
        'failed_rows':np.flatnonzero(~result['valid']).tolist(),
        'median_reduced_chi2':float(np.nanmedian(result['reduced_chi2'])),
        'rejected_samples':int(np.sum(result['requested_mask']&~result['fit_mask']&result['valid'][:,None])),
        'effective_background_pixel_count_range':[int(v) for v in np.percentile(result['fit_mask'][result['valid']].sum(axis=1),[0,100])],
        'source_sha256':{p.name:sha256(p) for p in source.glob('*.py')},
        'limitations':['Interpolates local sky plus host; not a galaxy decomposition or optimal extraction.',
            'Fits raw detector rows, not rectified constant-wavelength slices; tilted narrow lines need separate validation.',
            'Poisson plus read-noise model; full coefficient covariance propagated to boxcar sum; no model-choice uncertainty.',
            'Side bands are half-open; fractional aperture overlaps, invalid and saturated pixels are excluded.',
            'Aperture cosmic rays, bias/flat calibration and trace uncertainty are not corrected by this experiment.',
            'No calibrated flux delivery; uses the saved archive wavelength map.']}
    save_json(output/'background.json',qa)
    return qa
