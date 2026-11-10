"""PypeIt response from a raw standard; no archived IRAF sensitivity files."""
from pathlib import Path
import json
import numpy as np
from astropy import units as u
from astropy.io import fits
from .inventory import sha256


def fit_response_curve(wave, counts, ivar, good, metadata, standard):
    """PypeIt zeropoints/B-splines with intact boundary knots.

    PypeIt 1.14 standard_zeropoint removes masked knots including the padded
    boundary knots. With low-resolution spectra this can erase most of the
    fitted domain. Keep the mathematical padding; mask data, not boundary
    conditions. No response is evaluated outside the measured reference bracket.
    """
    from pypeit.core import flux_calib, fitting
    from pypeit.core.atmextinction import AtmosphericExtinction
    from astropy.stats import sigma_clipped_stats
    wave=np.asarray(wave,float)
    rate,rate_ivar,rate_mask=flux_calib.counts2Nlam(wave,counts,ivar,good,
        metadata['EXPTIME'],metadata['ESO TEL AIRM START'],
        AtmosphericExtinction.from_file('lasillaextinct.dat'))
    truth=np.interp(wave,np.asarray(standard['wave'],float),np.asarray(standard['flux'],float),
                    left=np.nan,right=np.nan)
    bad,stellar,telluric=flux_calib.get_mask(wave,rate,rate_ivar,rate_mask,
        mask_hydrogen_lines=True,mask_helium_lines=True,mask_telluric=True,hydrogen_mask_wid=40.)
    zp,zp_good=flux_calib.compute_zeropoint(wave,rate,bad & np.isfinite(truth),truth)
    fit_mask=zp_good & stellar & telluric
    if fit_mask.sum()<100:raise ValueError('too few continuum samples for a response')
    smooth=fitting.robust_fit(wave,zp,5,function='polynomial',in_gpm=fit_mask,
        minx=wave[good].min(),maxx=wave[good].max(),lower=3.,upper=3.,
        groupbadpix=False,grow=0,sticky=True,use_mad=True)
    _,_,scatter=sigma_clipped_stats(zp-smooth.eval(wave),mask=~fit_mask,
        cenfunc='median',stdfunc='mad_std',maxiters=10,sigma=3.)
    if not np.isfinite(scatter) or scatter<=0:raise ValueError('invalid response residual scale')
    spacing=float(np.median(wave[good]/400.)*20.)
    spline,accepted,_,_,status=fitting.iterative_bspline_fit(
        wave,zp,ivar=np.full(wave.shape,1./scatter**2),
        gpm=fit_mask,upper=3.,lower=3.,maxiter=35,
        kwargs_knots={'spacing':spacing},kwargs_reject={'maxrej':5})
    if status != 0 or spline is None:
        raise ValueError(f'PypeIt response spline did not converge (exit status {status})')
    fitted,support=spline.value(wave)
    accepted=np.asarray(accepted,bool)&fit_mask
    if accepted.sum()<100:raise ValueError('insufficient response continuum after rejection')
    # Spline padding is not physical extrapolation. Enforce the actually
    # accepted continuum bracket and retain missing/bad extraction intervals.
    valid=support & good & (wave>=wave[accepted].min()) & (wave<=wave[accepted].max())
    return fitted,valid,dict(engine='pypeit.core.fitting.iterative_bspline_fit',
        boundary_policy='intact padded knots; accepted continuum bracket only',
        knot_spacing_angstrom=spacing,accepted_continuum_samples=int(accepted.sum()),
        initial_continuum_samples=int(fit_mask.sum()),residual_scale_mag=float(scatter)),zp,accepted


def build_response(frame, spectrum, output, standard=None):
    from pypeit.core import flux_calib
    from pypeit import dataPaths
    h=frame['metadata']
    if standard is None:
        from .standard_reference import standard_reference
        standard=standard_reference(frame,Path(output).parent/'physical-references')
    if standard is None:
        raise ValueError('no physical standard reference within 100 arcsec')
    good=spectrum.OPT_MASK & (spectrum.OPT_COUNTS_IVAR>0) & (spectrum.OPT_COUNTS>0)
    if good.sum()<100:
        raise ValueError('too few valid standard pixels for a response')
    reference_wave=np.asarray(standard['wave'],dtype=float)
    if (np.min(spectrum.OPT_WAVE[good])<np.min(reference_wave)
            or np.max(spectrum.OPT_WAVE[good])>np.max(reference_wave)):
        raise ValueError('physical flux reference does not cover the extracted standard wavelengths')
    # NTT coordinates and PypeIt-bundled La Silla extinction, recorded explicitly.
    longitude,latitude=-70.7336,-29.2584
    extinct='lasillaextinct.dat'
    extinction=Path(dataPaths.extinction.get_file_path(extinct))
    wave=np.asarray(spectrum.OPT_WAVE,float)
    zp,valid,fit_details,measured_zp,accepted=fit_response_curve(wave,spectrum.OPT_COUNTS,
        spectrum.OPT_COUNTS_IVAR,good,h,standard)
    valid &= np.isfinite(zp) & (zp>5)&(zp<30)
    if valid.sum()<100:
        raise ValueError('PypeIt response has insufficient valid coverage')
    header=fits.Header({'MJD-OBS':h['MJD-OBS'],'FLUXCAL':'NATIVE','STDNAME':standard['name'],
                        'WAVEMED':'vacuum','LONGITUD':longitude,'LATITUDE':latitude,
                        'EXTFILE':extinct,'EXPTIME':h['EXPTIME'],'AIRMASS':h['ESO TEL AIRM START']})
    output=Path(output)
    fits.HDUList([fits.PrimaryHDU(header=header),fits.BinTableHDU.from_columns([
        fits.Column(name='WAVE',format='D',array=wave),fits.Column(name='ZEROPOINT',format='D',array=zp),
        fits.Column(name='VALID',format='L',array=valid),
        fits.Column(name='MEASURED_ZEROPOINT',format='D',array=measured_zp),
        fits.Column(name='FIT_ACCEPTED',format='L',array=accepted)],name='RESPONSE')]).writeto(output,checksum=True)
    record={'path':str(output.resolve()),'sha256':sha256(output),'mjd':h['MJD-OBS'],
        'selection':'explicit raw standard, physical reference matched within 100 arcsec',
        'standard_raw':frame['path'],'standard_sha256':frame['sha256'],
        'standard_name':standard['name'],'reference_file':str(standard['cal_file']),
        'reference_library':standard['std_source'],
        'fit_parameters':{'resolution':400.,'nresln':20.,'hydrogen_mask_wid_angstrom':40.,
                          'mask_helium_lines':True},
        'fit_details':fit_details,
        'valid_fraction':float(valid.mean()),
        'valid_vacuum_wavelength_bounds_angstrom':[float(wave[valid].min()),float(wave[valid].max())],
        'reference_details':{k:standard[k] for k in ('reference_url','reference_sha256',
            'wavelength_interpretation','coordinate_separation_arcsec','astrometry_reference',
            'coordinate_epoch_mjd','limitations') if k in standard},
        'extinction':{'path':str(extinction),'sha256':sha256(extinction)},
        'limitations':['Narrow-slit throughput and time-variable transparency remain uncorrected.',
                       'Response fit uncertainty is not included in the statistical spectrum errors.',
                       'Telluric absorption is not corrected.']}
    output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


def response_factor(waveair, path, exposure, airmass):
    """Electrons/pixel to cgs F_lambda per air Angstrom; mask unsupported response."""
    from pypeit.core import flux_calib
    from pypeit.core.atmextinction import AtmosphericExtinction
    from pypeit.core.wave import airtovac
    from pypeit.core.wavecal.wvutils import get_delta_wave
    waveair=np.asarray(waveair,dtype=float)
    wavevac=airtovac(waveair*u.AA).value
    with fits.open(path) as hdus:
        table=hdus['RESPONSE'].data;h=hdus[0].header
        # Evaluate the smooth fit only within its bracket. No extrapolation.
        valid_ref=table['VALID'] & np.isfinite(table['ZEROPOINT'])
        lo,hi=table['WAVE'][valid_ref].min(),table['WAVE'][valid_ref].max()
        valid=(wavevac>=lo)&(wavevac<=hi)&np.isfinite(wavevac)
        # A fit may have unsupported internal intervals as well as bad edges.
        # Both interpolation endpoints must be supported; never bridge such gaps.
        valid &= np.interp(wavevac,table['WAVE'],valid_ref.astype(float),left=0.,right=0.)>=1.-1e-9
        factor=np.full(wavevac.shape,np.nan)
        if valid.sum()<2:return factor,np.zeros_like(valid)
        zp=np.interp(wavevac[valid],table['WAVE'],table['ZEROPOINT'])
        response=flux_calib.Nlam_to_Flam(wavevac[valid],zp)*1e-17
        extinction=AtmosphericExtinction.from_file(h['EXTFILE'])
        correction=extinction.correction_factor(wavevac[valid],airmass)
        # PypeIt response converts counts/s/vacuum-A to F_lambda(vacuum).
        # Convert density to the delivered air grid using the exact width ratio.
        dv=get_delta_wave(wavevac,np.ones(wavevac.shape,dtype=bool))
        da=get_delta_wave(waveair,np.ones(waveair.shape,dtype=bool))
        factor[valid]=response*correction/exposure/dv[valid]*(dv[valid]/da[valid])
    return factor,valid&np.isfinite(factor)&(factor>0)
