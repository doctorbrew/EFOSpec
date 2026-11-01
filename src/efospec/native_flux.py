"""PypeIt response from a raw standard; no archived IRAF sensitivity files."""
from pathlib import Path
import json
import numpy as np
from astropy import units as u
from astropy.io import fits
from .inventory import sha256


def build_response(frame, spectrum, output, standard=None):
    from pypeit.core import flux_calib
    from pypeit import data
    h=frame['metadata']
    if standard is None:
        from .standard_reference import standard_reference
        standard=standard_reference(frame,Path(output).parent/'physical-references')
    if standard is None:
        raise ValueError('no physical standard reference within 100 arcsec')
    good=spectrum.OPT_MASK & (spectrum.OPT_COUNTS_IVAR>0) & (spectrum.OPT_COUNTS>0)
    if good.sum()<100:
        raise ValueError('too few valid standard pixels for a response')
    # NTT coordinates and PypeIt-bundled La Silla extinction, recorded explicitly.
    longitude,latitude=-70.7336,-29.2584
    extinct='lasillaextinct.dat'
    extinction=Path(data.get_extinctfile_filepath(extinct))
    _,table=flux_calib.sensfunc(spectrum.OPT_WAVE,spectrum.OPT_COUNTS,
        spectrum.OPT_COUNTS_IVAR,good,h['EXPTIME'],h['ESO TEL AIRM START'],standard,
        longitude,latitude,extinct,resolution=400.,nresln=20.,hydrogen_mask_wid=40.,
        mask_helium_lines=True)
    wave=np.asarray(table['SENS_WAVE'][0]);zp=np.asarray(table['SENS_ZEROPOINT_FIT'][0])
    valid=np.asarray(table['SENS_ZEROPOINT_FIT_GPM'][0]) & good & np.isfinite(zp) & (zp>5)&(zp<40)
    if valid.sum()<100:
        raise ValueError('PypeIt response has insufficient valid coverage')
    header=fits.Header({'MJD-OBS':h['MJD-OBS'],'FLUXCAL':'NATIVE','STDNAME':standard['name'],
                        'WAVEMED':'vacuum','LONGITUD':longitude,'LATITUDE':latitude,
                        'EXTFILE':extinct,'EXPTIME':h['EXPTIME'],'AIRMASS':h['ESO TEL AIRM START']})
    output=Path(output)
    fits.HDUList([fits.PrimaryHDU(header=header),fits.BinTableHDU.from_columns([
        fits.Column(name='WAVE',format='D',array=wave),fits.Column(name='ZEROPOINT',format='D',array=zp),
        fits.Column(name='VALID',format='L',array=valid)],name='RESPONSE')]).writeto(output,checksum=True)
    record={'path':str(output.resolve()),'sha256':sha256(output),'mjd':h['MJD-OBS'],
        'selection':'explicit raw standard, physical reference matched within 100 arcsec',
        'standard_raw':frame['path'],'standard_sha256':frame['sha256'],
        'standard_name':standard['name'],'reference_file':str(standard['cal_file']),
        'reference_library':standard['std_source'],
        'reference_details':{k:standard[k] for k in ('reference_url','reference_sha256','wavelength_interpretation','coordinate_separation_arcsec') if k in standard},
        'extinction':{'path':str(extinction),'sha256':sha256(extinction)},
        'limitations':['Narrow-slit throughput and time-variable transparency remain uncorrected.',
                       'Response fit uncertainty is not included in the statistical spectrum errors.',
                       'Telluric absorption is not corrected.']}
    output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


def response_factor(waveair, path, exposure, airmass):
    """Electrons/pixel to cgs F_lambda per air Angstrom; mask unsupported response."""
    from pypeit.core import flux_calib
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
        factor=np.full(wavevac.shape,np.nan)
        if valid.sum()<2:return factor,np.zeros_like(valid)
        zp=np.interp(wavevac[valid],table['WAVE'],table['ZEROPOINT'])
        response=flux_calib.Nlam_to_Flam(wavevac[valid],zp)*1e-17
        extinction=flux_calib.load_extinction_data(h['LONGITUD'],h['LATITUDE'],h['EXTFILE'])
        correction=flux_calib.extinction_correction(wavevac[valid]*u.AA,airmass,extinction)
        # PypeIt response converts counts/s/vacuum-A to F_lambda(vacuum).
        # Convert density to the delivered air grid using the exact width ratio.
        dv=get_delta_wave(wavevac,np.ones(wavevac.shape,dtype=bool))
        da=get_delta_wave(waveair,np.ones(waveair.shape,dtype=bool))
        factor[valid]=response*correction/exposure/dv[valid]*(dv[valid]/da[valid])
    return factor,valid&np.isfinite(factor)&(factor>0)
