"""Experimental fixed-profile extraction, with immutable recipes and covariance."""
from copy import deepcopy
from dataclasses import replace
import json
import re
from pathlib import Path
import numpy as np
from astropy import units as u
from astropy.io import fits
from .archive_calibration import rebin_density
from .inventory import sha256
from .joint import choose_background_degree, extract_joint
from .recipes import sky_mask, validate_recipe


def validate_joint_recipe(value, window, expected_inputs):
    if not isinstance(value,dict):raise ValueError('joint recipe must be an object')
    recipe=deepcopy(value)
    degree=recipe.pop('background_degree',None)
    if degree!='auto' and (type(degree) is not int or degree not in (0,1,2)):
        raise ValueError('background degree must be auto, 0, 1 or 2')
    if type(recipe.get('schema_version')) is not int or recipe['schema_version']!=2 or recipe.get('engine_version')!='efospec-joint-1':
        raise ValueError('joint recipe requires schema 2 and efospec-joint-1')
    if recipe.get('source_mode')!='manual' or not isinstance(recipe.get('objects'),list) or not 1<=len(recipe['objects'])<=2:
        raise ValueError('joint extraction requires one or two manually identified profiles')
    if recipe.get('sky',{}).get('mode')!='regions':
        raise ValueError('joint extraction requires explicit background regions')
    # Validate all v1 fields and each aperture without weakening its separation gate.
    base=deepcopy(recipe);base.update(schema_version=1,engine_version='1.14.0')
    for obj in recipe['objects']:
        if not isinstance(obj,dict) or not isinstance(obj.get('id'),str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}',obj['id']):
            raise ValueError('joint object IDs must be simple identifiers')
        single=deepcopy(base);single['objects']=[dict(obj,id='primary')]
        validate_recipe(single,window,expected_inputs)
    if recipe['objects'][0]['id']!='primary' or len({o['id'] for o in recipe['objects']})!=len(recipe['objects']):
        raise ValueError('joint source identities must be distinct with primary first')
    if np.min(sky_mask(recipe,window).sum(axis=1))<12:
        raise ValueError('joint extraction needs at least twelve sky pixels per row')
    recipe['background_degree']=value['background_degree']
    return recipe


def rectify_counts(data, variance, wave, good, grid):
    """Flux-conserving overlap, with squared weights and no bridging masked bins."""
    data,variance,wave,good=map(np.asarray,(data,variance,wave,good))
    if data.ndim!=2 or any(v.shape!=data.shape for v in (variance,wave,good)):
        raise ValueError('rectification planes must share a two-dimensional geometry')
    def widths(w):
        return np.diff(np.r_[w[0]-(w[1]-w[0])/2,(w[:-1]+w[1:])/2,w[-1]+(w[-1]-w[-2])/2])
    dw=widths(np.asarray(grid));out=[];outvar=[];valid=[]
    for col in range(data.shape[1]):
        width=widths(wave[:,col])
        f,v,m=rebin_density(wave[:,col],data[:,col]/width,variance[:,col]/width**2,good[:,col],grid)
        out.append(f*dw);outvar.append(v*dw**2);valid.append(m)
    return {'data':np.array(out).T,'variance':np.array(outvar).T,'valid':np.array(valid).T,
            'spectral_covariance':'adjacent output bins correlated; diagonal only'}


def fit_exposure(exposure, recipe):
    """Fit the observed window; source identity and profile widths are operator inputs."""
    recipe=validate_joint_recipe(recipe,exposure.window,exposure.hashes)
    context=exposure.context;data=context.data;wave=context.waveair
    if context.processed:
        ivar=context.processed['ivar'];good=~context.processed['bad_pixels'] & (ivar>0)
        variance=np.divide(1,ivar,out=np.full_like(ivar,np.nan),where=ivar>0)
    else:
        variance=np.maximum(data,0)+context.frame['metadata']['ESO DET OUT1 RON']**2
        good=np.isfinite(data)&(exposure.images.get('mask',np.zeros(data.shape))==0)
    grid=wave[:,data.shape[1]//2]
    rect=rectify_counts(data,variance,wave,good,grid)
    spatial=np.arange(data.shape[1])+exposure.window.origin[1]
    template=exposure.images['trace']+exposure.window.origin[1]
    profiles=[];traces=[]
    sky=sky_mask(recipe,exposure.window)
    for obj in recipe['objects']:
        anchor=obj['spec']-exposure.window.origin[0]
        trace=template+obj['spat']-np.interp(anchor,np.arange(len(template)),template)
        traces.append(trace)
        p=np.exp(-.5*((spatial[None,:]-trace[:,None])/(obj['fwhm']/2.354820045))**2)
        profiles.append(p/p.sum(axis=1)[:,None])
        sky &= abs(spatial[None,:]-trace[:,None])>max(obj['radius'],3*obj['fwhm'])
    validrows=(sky&rect['valid']).sum(axis=1)>=12
    # Rectification boundaries may be incomplete. Keep these rows invalid, never extrapolate.
    if validrows.sum()<20:raise ValueError('fewer than twenty rows have sufficient valid sky')
    degree=recipe['background_degree']
    selection=choose_background_degree(rect['data'][validrows],rect['variance'][validrows],
                                       (sky&rect['valid'])[validrows])
    chosen=selection['degree'] if degree=='auto' else degree
    fits_by_degree={}
    for order in sorted(set(selection['admissible_degrees']+[chosen])):
        # The solver handles missing source pixels, but requires valid selected sky.
        fits_by_degree[order]=extract_joint(rect['data'][validrows],rect['variance'][validrows],
            np.array(profiles)[:,validrows],(sky&rect['valid'])[validrows],background_degree=order)
    fit=fits_by_degree[chosen]
    if not fit['valid'].any():raise ValueError('joint profiles are degenerate or no rows pass')
    return dict(rectified=rect,grid=grid,rows=validrows,fit=fit,alternatives=fits_by_degree,
                background_selection=selection,degree=chosen,profiles=np.array(profiles),traces=traces,
                sky=sky,recipe=recipe)


def reextract_joint(run, product, recipe, output, reference_root=None, *, render_report=True):
    import pypeit
    from pypeit.core.wave import airtovac
    from pypeit.specobjs import SpecObjs
    from pypeit.specobj import SpecObj
    from .revisions import Exposure
    from .products import export_spectrum
    exposure=Exposure(run,product,reference_root)
    recipe=validate_joint_recipe(recipe,exposure.window,exposure.hashes)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    for sub in ('products','native','qa','QA/PNGs'):(output/sub).mkdir(parents=True)
    (output/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n')
    manifest=dict(schema_version=1,status='EXPERIMENTAL',method='fixed_profile_joint_extraction',
        input_dir=exposure.manifest['input_dir'],output_dir=str(output),parent_run=str(exposure.run),
        pypeit_version=pypeit.__version__,
        parent_product=product,recipe_sha256=sha256(output/'recipe.json'),results=[],errors=[],skipped=[],
        limitations=['Fixed Gaussian profiles share the measured trace curvature; extended host morphology is not inferred.',
          'Errors include conditional source covariance, not profile uncertainty or spectral resampling covariance.',
          'Background alternatives are saved separately; differences are not added as independent random errors.'])
    from .run_record import snapshot_sources
    manifest['source_sha256']=snapshot_sources(output)
    try:
        model=fit_exposure(exposure,recipe);fit=model['fit'];rows=model['rows'];grid=model['grid']
        nr,nx=exposure.context.data.shape;ns=len(recipe['objects'])
        fullflux=np.full((ns,nr),np.nan);fullcov=np.full((nr,ns,ns),np.nan)
        fullflux[:,rows]=fit['flux'].T;fullcov[rows]=fit['covariance']
        fitvalid=np.zeros(nr,bool);fitvalid[rows]=fit['valid']
        fitflags=np.full(nr,'insufficient_sky',dtype='U30');fitflags[rows]=fit['flags']
        chi2=np.full(nr,np.nan);chi2[rows]=fit['reduced_chi2']
        alt={f'flux_degree_{order}':value['flux'] for order,value in model['alternatives'].items()}
        np.savez_compressed(output/'native/joint-covariance.npz',waveair=grid,flux=fullflux,
            covariance=fullcov,valid_rows=rows,fit_valid=fitvalid,fit_flags=fitflags,reduced_chi2=chi2,
            source_ids=np.array([o['id'] for o in recipe['objects']]),
            profiles=model['profiles'],background_degree=model['degree'],**alt)
        summary={'background_selection':model['background_selection'],'chosen_degree':model['degree'],
                 'conditional_uncertainty':fit['uncertainty_scope'],'spectral_covariance':model['rectified']['spectral_covariance'],
                 'valid_fraction':float(np.mean(fit['valid'])),'profile_model':'fixed_gaussian_shared_trace',
                 'flux_unit':'electrons per rectified spectral bin','covariance_unit':'electrons squared',
                 'background_alternative_degrees':list(model['alternatives'])}
        # Save original detector pixels for honest 2D diagnostics and exact recipe replay.
        # Only the fitted background/model are interpolated back for their overlay.
        skyrect=np.full((nr,nx),np.nan);objrect=skyrect.copy()
        skyrect[rows]=fit['background'];objrect[rows]=fit['model']-fit['background']
        skyimage=np.column_stack([np.interp(exposure.context.waveair[:,j],grid,skyrect[:,j]) for j in range(nx)])
        objimage=np.column_stack([np.interp(exposure.context.waveair[:,j],grid,objrect[:,j]) for j in range(nx)])
        from pypeit.images.imagebitmask import ImageBitMaskArray
        mask=ImageBitMaskArray(exposure.context.data.shape)
        mask.mask[:]=exposure.images.get('mask',0)
        objects={}
        for i,obj in enumerate(recipe['objects']):
            s=SpecObj('MultiSlit','DET01',OBJTYPE='science',SLITID=exposure.native.SLITID);s.OBJID=i+1;s.NAME=f'JOINT-{obj["id"]}';s.SPAT_PIXPOS=float(np.median(model['traces'][i])-exposure.window.origin[1])
            s.TRACE_SPAT=model['traces'][i]-exposure.window.origin[1];s.BOX_RADIUS=obj['radius']
            s.OPT_WAVE=airtovac(grid*u.AA).value;s.BOX_WAVE=s.OPT_WAVE.copy()
            s.OPT_COUNTS=fullflux[i];s.OPT_COUNTS_IVAR=np.divide(1,fullcov[:,i,i],out=np.zeros(nr),where=fullcov[:,i,i]>0)
            valid=np.zeros(nr,dtype=bool);valid[rows]=fit['valid'];s.OPT_MASK=valid.copy()
            s.OPT_COUNTS_SIG=np.sqrt(np.maximum(fullcov[:,i,i],0))
            box=np.full(nr,np.nan);boxvar=box.copy();skysum=box.copy()
            # Deblended aperture sum is a linear operator on the same data, including
            # uncertainty from subtracting the jointly fitted background/companion.
            from numpy.polynomial.legendre import legvander
            poly=legvander(np.linspace(-1,1,nx),model['degree'])
            for k,row in enumerate(np.flatnonzero(rows)):
                if not fit['valid'][k]:continue
                aperture=(abs(np.arange(nx)-s.TRACE_SPAT[row])<=obj['radius']).astype(float)
                design=np.column_stack([model['profiles'][:,row].T,poly]);other=design.copy();other[:,i]=0
                operator=aperture-aperture@other@fit['operator'][k]
                use=model['rectified']['valid'][row] & np.isfinite(model['rectified']['variance'][row])
                clean=abs(model['rectified']['data'][row]-fit['model'][k])<=6*np.sqrt(model['rectified']['variance'][row])
                if np.any((aperture>0)&(~use|~clean)):valid[row]=False;continue
                box[row]=operator@np.where(use,model['rectified']['data'][row],0)
                boxvar[row]=operator**2@np.where(use,model['rectified']['variance'][row],0)
                skysum[row]=aperture@fit['background'][k]
            s.BOX_COUNTS=box;s.BOX_COUNTS_IVAR=np.divide(1,boxvar,out=np.zeros(nr),where=boxvar>0)
            s.BOX_COUNTS_SIG=np.sqrt(boxvar);s.BOX_MASK=valid&np.isfinite(box);s.OPT_COUNTS_SKY=skysum
            s.BOX_COUNTS_SKY=skysum;s.FWHM=float(obj['fwhm']);s.FWHMFIT=np.full(nr,obj['fwhm']);objects[obj['id']]=SpecObjs([s])
        engine={'method':'fixed_profile_joint_extraction',
            'objects':objects,'found':[v[0] for v in objects.values()],
            'arrays':[skyimage,objimage,exposure.images['ivar'],mask],
            'selection':{'sky_input_mask':model['sky'],'onslit':np.ones((nr,nx),dtype=bool),
                         'sky_mask_stage':'joint_background_selection_before_profile_fit'},
            'sky_policy':f'joint_polynomial_degree_{model["degree"]}'}
        for obj in recipe['objects']:
            identity=obj['id'];basename=exposure.basename+('' if identity=='primary' else '_obj_'+identity)
            result=export_spectrum(replace(exposure.context,hint=obj['spat']-99,
                hint_info={'association':'operator_selected','object_id':identity,'requested':obj}),
                engine,identity,output,basename,label=obj['label'])
            result.update(object_id=identity,joint=summary)
            with fits.open(result['product'],mode='update') as hdus:
                hdus[0].header['EXTRACT']='JOINTFIX';hdus[0].header['BANDID1']='fixed-profile joint flux'
                hdus[0].header['BANDID2']='deblended boxcar flux'
                hdus[0].header['HISTORY']='Conditional profile errors; source covariance in native/joint-covariance.npz'
            manifest['results'].append(result)
        if Exposure(run,product,reference_root).hashes!=exposure.hashes:
            raise ValueError('input changed during joint extraction')
    except Exception as exc:
        manifest['errors'].append({'error':str(exc)});raise
    finally:
        (output/'run.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    if render_report:
        from .report import build_report
        manifest['report']=build_report(output)
        (output/'run.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    return manifest
