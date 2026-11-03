"""Raw He–Ar identification with physical grism bounds and held-out checks.

Independent wavelength source: ESO EFOSC2 manual 4.2, Table 17 (air Angstroms).
https://www.eso.org/sci/facilities/lasilla/instruments/efosc/doc/manual/EFOSC2manual_v4.2.pdf
No archived pixel positions, IRAF databases, or wavelength templates are read.
The broad search bounds describe centered slits in 2x2 mode, not other grisms.
"""
import itertools
import numpy as np
from numpy.polynomial import Polynomial


ATLAS_AIR = (3888.646,4471.479,4713.146,4921.931,5015.680,5875.621,
             6678.151,6965.430,7065.190,7272.930,7383.980,7635.106,
             7723.984,7948.176,8115.311,8264.522,8521.442,8667.944,9122.967)
BOUNDS = {'Gr13': ((5900.,7100.), (4.5,6.5)),
          'Gr11': ((4950.,5950.), (3.4,4.8))}


def atlas():
    from astropy import units as u
    from astropy.table import Table
    from pypeit.core.wave import airtovac
    helium = {3888.646,4471.479,4713.146,4921.931,5015.680,5875.621,6678.151,7065.190}
    # PypeIt 1.14 names its fit-eligibility flag NIST. The physical source here
    # remains ESO Table 17; this flag does not claim a separate NIST lookup.
    return Table({'wave':airtovac(np.array(ATLAS_AIR)*u.AA).value,
                  'ion':['HeI' if value in helium else 'ArI' for value in ATLAS_AIR],
                  'NIST':np.ones(len(ATLAS_AIR),int)})


def check_physical_range(wave, grism):
    from .native_wavelength import GRISMS, ENDPOINT_TOLERANCE
    if grism not in BOUNDS:
        raise ValueError('native wavelength identification enables only grism Gr11 or Gr13')
    wave=np.asarray(wave,float)
    if wave.ndim!=1 or len(wave)<20 or not np.isfinite(wave).all() or np.any(np.diff(wave)<=0):
        raise ValueError('wavelength solution must be finite and strictly increasing')
    center, dispersion=BOUNDS[grism]
    step=np.diff(wave)
    if not (center[0]<np.median(wave)<center[1] and np.all((step>dispersion[0])&(step<dispersion[1]))):
        raise ValueError('wavelength solution falls outside physical grism bounds')
    low, high, _ = GRISMS[grism]
    if abs(wave[0]-low)>ENDPOINT_TOLERANCE or abs(wave[-1]-high)>ENDPOINT_TOLERANCE:
        raise ValueError('wavelength solution falls outside the shared detector range gate')


def _patterns(centroids, references, length, grism):
    """Match curved patterns spanning the detector, then retain unique ID sets."""
    center, dispersion=BOUNDS[grism]
    triples=np.array(list(itertools.combinations(np.arange(len(centroids)),3)))
    if not len(triples):
        return []
    p=centroids[triples]
    triples=triples[(np.ptp(p,axis=1)>.6*length)&(p[:,1]-p[:,0]>.18*length)
                    &(p[:,2]-p[:,1]>.18*length)]
    reftriples=np.array(list(itertools.combinations(references,3)))
    reftriples=reftriples[np.ptp(reftriples,axis=1)>.6*length*dispersion[0]]
    candidates={}
    for triple in triples:
        pixels=centroids[triple]
        ratio=(pixels[1]-pixels[0])/(pixels[2]-pixels[0])
        guesses=reftriples[abs((reftriples[:,1]-reftriples[:,0])/np.ptp(reftriples,axis=1)-ratio)<.04]
        for guess in guesses:
            poly=Polynomial.fit(pixels,guess,2,domain=[0,length-1])
            derivative=poly.deriv()(np.linspace(0,length-1,9))
            if not (center[0]<poly((length-1)/2)<center[1]
                    and np.all((derivative>dispersion[0])&(derivative<dispersion[1]))):
                continue
            delta=abs(poly(centroids)[:,None]-references[None,:])
            match,accepted=delta.argmin(axis=1),delta.min(axis=1)<8.
            if accepted.sum()<8 or len(set(match[accepted]))!=accepted.sum():
                continue
            for _ in range(3):
                poly=Polynomial.fit(centroids[accepted],references[match[accepted]],3,domain=[0,length-1])
                delta=abs(poly(centroids)[:,None]-references[None,:])
                match,accepted=delta.argmin(axis=1),delta.min(axis=1)<3.
                if accepted.sum()<8:
                    break
            if accepted.sum()<8 or len(set(match[accepted]))!=accepted.sum():
                continue
            rms=float(np.sqrt(np.mean((poly(centroids[accepted])-references[match[accepted]])**2)))
            key=tuple(zip(np.flatnonzero(accepted),match[accepted]))
            candidates[key]=(int(accepted.sum()),rms,accepted.copy(),match.copy())
    return sorted(candidates.values(),key=lambda item:(-item[0],item[1]))


def identify_spectrum(spectrum, grism, *, filter_name='Free', fwhm=4.2, nonlinear_counts=1e10):
    """Use PypeIt centroids/fitting with an independently constrained ID seed.

    Returns a native PypeIt WaveFit in vacuum Angstroms and explicit QA. The
    reference-line bracket, not polynomial extrapolation, defines valid output.
    Whole-line hold-outs assess the fit; contemporary sky lines must also be
    checked independently by the science runner.
    """
    from pypeit.core.arc import detect_lines
    from pypeit.core.wavecal.wv_fitting import iterative_fitting
    from .native_wavelength import validate_solution
    if grism not in BOUNDS:
        raise ValueError('unsupported native wavelength grism')
    spectrum=np.asarray(spectrum,float)
    if spectrum.ndim!=1 or len(spectrum)<100 or not np.isfinite(spectrum).all():
        raise ValueError('raw arc spectrum must be a finite 1D array')
    if not np.isfinite(fwhm) or fwhm<=0 or not np.isfinite(nonlinear_counts) or nonlinear_counts<=0:
        raise ValueError('invalid line width or detector nonlinearity limit')
    amp,_,cent,_,_,good,_,significance=detect_lines(spectrum,fwhm=fwhm,sigdetect=10.)
    cent=cent[good];amp=amp[good];significance=significance[good]
    linear=spectrum[np.clip(np.rint(cent).astype(int),0,len(spectrum)-1)]<nonlinear_counts
    cent,significance=cent[linear],significance[linear]
    # Bound pathological cosmic-ray/feature-rich inputs before combinatorics.
    if len(cent)>40:
        cent=cent[np.argsort(significance)[-40:]]
    cent=np.sort(cent)
    if len(cent)<8:
        raise ValueError('insufficient unsaturated raw arc lines')
    lines=atlas();references=np.asarray(lines['wave'])
    patterns=_patterns(cent,references,len(spectrum),grism)
    solutions=[]
    for _,_,accepted,match in patterns[:8]:
        fit=iterative_fitting(spectrum,cent,np.flatnonzero(accepted),references[match[accepted]],
            lines,disp=np.mean(BOUNDS[grism][1]),n_first=3,n_final=4,match_toler=.6)
        if fit is None:
            continue
        # Revisit blue lines after the high-order fit removes the coarse
        # quadratic/cubic approximation error. All IDs still come from the atlas.
        delta=abs(fit.pypeitfit.eval(cent/(len(spectrum)-1))[:,None]-references[None,:])
        keep=delta.min(axis=1)<1.5
        nearest=delta.argmin(axis=1)
        if keep.sum()>=8 and len(set(nearest[keep]))==keep.sum():
            fit=iterative_fitting(spectrum,cent,np.flatnonzero(keep),references[nearest[keep]],
                lines,disp=np.mean(BOUNDS[grism][1]),n_first=4,n_final=4,match_toler=.3,input_only=True)
        if fit is None:
            continue
        try:
            wave=fit.pypeitfit.eval(np.arange(len(spectrum))/(len(spectrum)-1))
            check_physical_range(wave,grism)
        except ValueError:
            continue
        mask=fit.pypeitfit.gpm.astype(bool)
        pixels,ids=fit.pixel_fit[mask],fit.wave_fit[mask]
        if len(ids)<8 or np.ptp(pixels)<.6*len(spectrum):
            continue
        residual=fit.pypeitfit.eval(pixels/(len(spectrum)-1))-ids
        hold=np.arange(len(ids))%4==2
        if (~hold).sum()<6:
            continue
        held_fit=Polynomial.fit(pixels[~hold],ids[~hold],4)
        held_residual=held_fit(pixels[hold])-ids[hold]
        rms=float(np.sqrt(np.mean(residual**2)))
        held_rms=float(np.sqrt(np.mean(held_residual**2)))
        if rms>1. or held_rms>1.5 or np.max(abs(held_residual))>2.5:
            continue
        try:
            acceptance=validate_solution(fit,grism,filter_name=filter_name)
        except ValueError:
            continue
        qa=dict(source='ESO_EFOSC2_manual_4.2_table_17_physical_wavelengths',
            medium='vacuum',unit='Angstrom',grism=grism,n_lines=len(ids),
            reference_lines_vacuum=ids.tolist(),pixel_centroids=pixels.tolist(),
            rms_angstrom=rms,held_out_rms_angstrom=held_rms,
            held_out_lines_vacuum=ids[hold].tolist(),held_out_residuals_angstrom=held_residual.tolist(),
            rms_pixels=float(fit.rms),wavelength_range_vacuum=wave[[0,-1]].tolist(),
            nonlinear_counts=float(nonlinear_counts),line_fwhm_pixels=float(fwhm),
            physical_bounds={'center_vacuum_angstrom':BOUNDS[grism][0],
                             'dispersion_angstrom_per_binned_pixel':BOUNDS[grism][1]})
        qa['shared_acceptance']=acceptance
        solutions.append((fit,qa,wave))
    if not solutions:
        raise ValueError('raw arc lines do not establish a physically validated wavelength solution')
    solutions.sort(key=lambda item:(-item[1]['n_lines'],item[1]['held_out_rms_angstrom']))
    best=solutions[0]
    for other in solutions[1:]:
        if other[1]['n_lines']>=best[1]['n_lines']-1 and np.median(abs(other[2]-best[2]))>3.:
            raise ValueError('ambiguous raw-arc line identification')
    return best[0],best[1]
