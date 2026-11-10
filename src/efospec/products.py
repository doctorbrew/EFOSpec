"""One legacy-compatible exporter for automatic and manual EFOSC2 extraction."""
from dataclasses import dataclass
from pathlib import Path
import json

import numpy as np
from astropy import units as u
from astropy.io import fits

from .archive_calibration import sensitivity_factor, rebin_density
from .inventory import sha256


@dataclass(frozen=True)
class PreparedExposure:
    """Fixed input/calibration context; image values are electrons and air Angstroms."""
    frame: dict
    reference_root: Path
    detector: object
    data: np.ndarray
    waveair: np.ndarray
    spatial_origin: int
    raw_y_origin: int
    hint: float
    hint_info: dict
    arc_qa: dict
    sensitivity: Path
    shift: float
    sky_qa: dict
    calibration: dict = None
    processed: dict = None


def export_spectrum(context, engine, identity, output, basename, *, label=None):
    """Write one requested source; retain primary naming and all four flux bands."""
    import pypeit
    from pypeit.specobjs import SpecObjs
    from pypeit.core.wave import vactoair
    from .pypeit_adapter import EFOSpecEFOSC2Spectrograph

    if Path(basename).name != basename or not basename or basename in {'.', '..'}:
        raise ValueError('product basename must be a plain filename')
    output = Path(output)
    filename = basename+'_f.fits'
    if (output/'products'/filename).exists():
        raise FileExistsError('product already exists; choose a fresh revision directory')
    native_calibration = context.calibration is not None
    joint = engine.get('method') == 'fixed_profile_joint_extraction'
    frame = context.frame
    path = Path(frame['path'])
    h, setup = dict(frame['metadata']), frame['setup']
    if label is not None:
        h['OBJECT'] = label
    reference_root, sensitivity = Path(context.reference_root), Path(context.sensitivity)
    det, data, w = context.detector, context.data, context.waveair
    xlo, ymin = context.spatial_origin, context.raw_y_origin
    xhi = xlo+data.shape[1]
    hint, hint_info = context.hint, context.hint_info
    arc_qa, shift, sky_qa = context.arc_qa, context.shift, context.sky_qa
    inst = EFOSpecEFOSC2Spectrograph()
    result, sky_selection = engine['arrays'], engine['selection']
    candidates = [{'name':s.NAME, 'trimmed_spatial_pixel':float(s.SPAT_PIXPOS+xlo)}
                  for s in engine['found']]
    objects = engine['objects'][identity]
    target_name = objects[0].NAME
    s = objects[0]
    s.DETECTOR = det
    native = output/'native'/('spec1d_'+basename+'.fits')
    subheader = {k:h[k] for k in ('RA','DEC','EXPTIME','DATE-OBS','INSTRUME','MJD-OBS')}
    subheader.update({'TARGET':h['OBJECT'],'PYP_SPEC':inst.name,'PYPELINE':'MultiSlit',
                     'WAVEMED':'vacuum','SPECSYS':'TOPOCENT','EPSTATUS':'EXPERIMENTAL',
                     'EXTRACT':'JOINTFIX' if joint else 'PYPEIT'})
    objects.write_to_fits(subheader,str(native),overwrite=False)
    check = SpecObjs.from_fitsfile(str(native))
    if len(check)!=1 or not np.array_equal(check[0].OPT_COUNTS,s.OPT_COUNTS,equal_nan=True):
        raise ValueError('native spectrum did not round-trip')
    diagnostic_path=None
    if 'diagnostic_context' in engine:
        from .pypeit_diagnostics import write_spec2d
        from pypeit.core.wave import airtovac
        diagnostics=engine['diagnostic_context']
        diagnostic_path=write_spec2d(output/'native'/('spec2d_'+basename+'.fits'),
            diagnostics['science'],diagnostics['slits'],airtovac(w*u.AA).value,
            diagnostics['tilts'],result[0],arrays=result,raw_origin=(ymin,99+xlo),
            stage='extracted')
    np.savez_compressed(output/'native'/(basename+'_images.npz'),data=data,
        sky=result[0],object_model=result[1],ivar=result[2],mask=result[3].mask, waveair=w,
        trace=s.TRACE_SPAT,spatial_origin=xlo,raw_y_origin=ymin, **sky_selection,
        **({('processed_'+k):v for k,v in context.processed.items()} if context.processed else {}))
    extinction = (Path(context.calibration['extinction']['path']) if native_calibration
                  else Path(reference_root)/'standard/extinction/extinction_lasilla.dat')
    wave = vactoair(s.OPT_WAVE*u.AA).value
    # Stay inside the fitted reference-line bracket (shifted to this science exposure).
    low, high = np.min(arc_qa['reference_lines'])+shift, np.max(arc_qa['reference_lines'])+shift
    step = 5.5 if setup['grism']=='Gr13' else 4.0
    grid = np.arange(np.ceil(low/step)*step,high-step,step)
    bands, variances, masks = [],[],[]
    for kind in ('OPT','BOX'):
        kw = vactoair(s[kind+'_WAVE']*u.AA).value
        if native_calibration:
            from .native_flux import response_factor
            factor, valid = response_factor(kw,sensitivity,h['EXPTIME'],h['ESO TEL AIRM START'])
        else:
            factor, valid = sensitivity_factor(kw,sensitivity,extinction,h['EXPTIME'],
                                              h['ESO TEL AIRM START'],h['ESO DET OUT1 GAIN'])
        ivar = s[kind+'_COUNTS_IVAR']
        var = np.divide(1,ivar,out=np.full_like(ivar,np.nan),where=ivar>0)
        good = valid & s[kind+'_MASK'] & (ivar>0) & (kw>=low) & (kw<=high)
        flux, variance, mask = rebin_density(kw,s[kind+'_COUNTS']*factor,var*factor**2,good,grid)
        bands.append(flux); variances.append(variance); masks.append(mask)
        if kind=='OPT':
            sky_flux,_,sky_mask = rebin_density(kw,s.OPT_COUNTS_SKY*factor,var*factor**2,good,grid)
    products = np.array([bands[0],bands[1],sky_flux,np.sqrt(variances[0])])[:,None,:]
    header = fits.Header(subheader)
    header['ORIGOBJ']=frame['metadata']['OBJECT']
    header['OBJECT']=h['OBJECT']; header['CRVAL1']=float(grid[0]); header['CRPIX1']=1.
    header['CD1_1']=step; header['CDELT1']=step; header['CTYPE1']='LINEAR'
    header['CUNIT1']='Angstrom'; header['WAVEMED']='air'; header['DC-FLAG']=0
    header['BUNIT']='erg / (s cm2 Angstrom)'; header['GRISM']=setup['grism']
    header['FILTER']=setup['filter'];header['SLIT']=setup['slit'];header['FILETYPE']=22208
    header['ARCFILE']=h['ARCFILE'];header['EXPTIME']=h['EXPTIME'];header['AIRMASS']=h['ESO TEL AIRM START']
    header['PROV1']=h['ARCFILE'];header['TRACE1']=native.name
    header['QUALITY']='Rapid';header['PYPEITV']=pypeit.__version__
    header['SENSFUN']=sensitivity.name;header['ARCREF']=Path(arc_qa['arc']).name
    header['WAVSHIFT']=shift;header['FLUXCAL']='NATIVE' if native_calibration else 'ARCHIVE';header['TELLURIC']='NONE'
    header['BANDID1']='optimal flux';header['BANDID2']='boxcar flux'
    header['BANDID3']='sky flux in optimal aperture';header['BANDID4']='optimal flux uncertainty'
    center = float(np.nanmedian(s.TRACE_SPAT)+xlo)+1  # IRAF one-based aperture coordinates
    header['APNUM1']=f'1 1 {center-float(s.BOX_R_PIX):.3f} {center+float(s.BOX_R_PIX):.3f}'
    if native_calibration:
        header['HISTORY']='Experimental raw bias/flat/HeAr and observed standard response.'
        header['HISTORY']='No telluric or slit-loss correction. Response uncertainty not propagated.'
    else:
        header['HISTORY']='Experimental archive calibration bridge.'
        header['HISTORY']='No bias/flat/dark/overscan or telluric correction. Not a certified ESO product.'
    header['HISTORY']=('Fixed-profile joint solver; conditional source covariance saved separately.' if joint
                       else 'PypeIt sky, trace, optimal and boxcar extraction.')
    header['HISTORY']='Bin-overlap resampling; inter-wavelength covariance not stored.'
    final = output/'products'/filename
    fits.HDUList([fits.PrimaryHDU(products,header),
                  fits.ImageHDU(np.array([masks[0],masks[1],sky_mask,masks[0]],dtype=np.uint8),name='VALID')]
                 ).writeto(final,checksum=True)
    np.savetxt(final.with_suffix('.asci'),np.column_stack([grid,bands[0]]),fmt='%.8e')
    snmask = s.OPT_MASK & (s.OPT_COUNTS_IVAR>0) & (wave>4000)&(wave<8500)
    qa = {'raw':str(path),'raw_sha256':frame['sha256'],'object':h['OBJECT'],
          'role':frame['role'],'grism':setup['grism'],'slit':setup['slit'],
          'date_obs':h['DATE-OBS'],'exptime_s':h['EXPTIME'],
          'arc':arc_qa,'sky_flexure':sky_qa,
          'sensitivity':{'path':str(sensitivity),'sha256':sha256(sensitivity),
                         'mjd':fits.getheader(sensitivity)['MJD-OBS'],
                         'selection':'nearest archived MJD, matching grism/filter; slit ignored as legacy'},
          'extinction':{'path':str(extinction),'sha256':sha256(extinction)},
          'target':{**hint_info,'hint_trimmed_pixel':hint,'candidates':candidates,
                    'selected':target_name,'median_trace_trimmed_pixel':float(np.median(s.TRACE_SPAT)+xlo)},
          'native_spec1d':str(native),'product':str(final),
          'processing':{'trim_numpy_yx':[ymin,ymin+data.shape[0],99,950],
                        'spatial_crop_in_trim':[xlo,xhi], 'gain_e_per_adu':h['ESO DET OUT1 GAIN'],
                        'read_noise_e':h['ESO DET OUT1 RON'], 'airmass':h['ESO TEL AIRM START'],
                        'bias':False,'flat':False,'overscan':False,'dark':False,'cosmic_ray_premask':False,
                        'spectral_flexure':'two-line sky offset before native extraction',
                        'sky_bspline_spacing':1.0,'findobj_snr_threshold':5.,'findobj_maxnumber':3,
                        'native_counts_unit':'electrons per spectral pixel',
                        'output_step_angstrom':step},
          'median_native_snr_4000_8500':float(np.median(s.OPT_COUNTS[snmask]*np.sqrt(s.OPT_COUNTS_IVAR[snmask]))),
          'valid_flux_fraction':float(np.mean(masks[0])), 'flux_band_order':['optimal','boxcar','sky','sigma'],
          'output_wavelength_medium':'air','native_wavelength_medium':'vacuum','reference_frame':'topocentric',
          'status':'EXPERIMENTAL','raw_unchanged':sha256(path)==frame['sha256']}
    if diagnostic_path:
        qa['native_spec2d']=diagnostic_path
        qa['native_spec2d_sha256']=sha256(Path(diagnostic_path))
    if native_calibration:
        qa['calibration'] = context.calibration
        qa['sensitivity'] = context.calibration['sensitivity']
        qa['extinction'] = context.calibration['extinction']
        qa['images_sha256'] = sha256(output/'native'/(basename+'_images.npz'))
        qa['processing'].update(bias=True,flat=True,cosmic_ray_premask=True,
            trim_numpy_yx=[ymin,ymin+data.shape[0],99+xlo,99+xhi],
            variance='PypeIt raw processing propagated variance',
            spectral_flexure=sky_qa.get('policy','unmeasured'))
    qa['processing']['sky_policy'] = engine['sky_policy']
    if 'source_selection' in engine:
        qa['target']['selection_policy'] = engine['source_selection']
    if 'background_fit' in engine:
        qa['processing']['background_fit'] = engine['background_fit']
    if not qa['raw_unchanged']:
        raise ValueError('raw input changed during processing')
    (output/'qa'/(basename+'.json')).write_text(json.dumps(qa,indent=2,allow_nan=False)+'\n')
    return qa

