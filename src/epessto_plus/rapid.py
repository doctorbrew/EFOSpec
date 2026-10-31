"""Experimental rapid reduction: archive calibration bridge + PypeIt extraction.

This deliberately does not masquerade as a native PypeIt calibration run.
Only the inspected 2x2 EFOSC2 Gr11/Gr13 Free-filter mode is enabled.
"""
import json
import re
import sys
import traceback
from pathlib import Path
import shutil

import numpy as np
from astropy import units as u
from astropy.io import fits

from .archive_calibration import fit_arc, sky_flexure, sensitivity_factor, rebin_density
from .inventory import inventory, sha256
from .naming import science_stem, product_name


def target_hint(frame, legacy_root):
    """Use historical aperture geometry only; never use its measured flux."""
    h, setup = frame['metadata'], frame['setup']
    stem = science_stem(h['OBJECT'], h['DATE-OBS'], setup['grism'], setup['filter'], setup['slit'])
    for p in sorted(Path(legacy_root).rglob('ap'+stem+'_*')):
        match = re.search(r'^\s*center\s+([\d.]+)', p.read_text(), flags=re.M)
        if match:
            return float(match[1])-1, {'source':str(p), 'sha256':sha256(p),
                                       'association':'historical_aperture'}
    for p in sorted(Path(legacy_root).rglob(stem+'_*_ex.fits')):
        header = fits.getheader(p)
        if header.get('DATE-OBS') != h['DATE-OBS']:
            continue
        values = str(header.get('APNUM1','')).split()
        if len(values) == 4:
            return (float(values[2])+float(values[3]))/2-1, {
                'source':str(p), 'sha256':sha256(p), 'association':'historical_aperture'}
    # This is an acquisition-position hypothesis, not an astrometric identity.
    return 449., {'source':'nominal acquisition position in this dataset',
                  'association':'UNVERIFIED_target_association'}


def select_archive(frame, reference_root):
    setup, h = frame['setup'], frame['metadata']
    if (setup['grism'] not in {'Gr11','Gr13'} or setup['filter'] != 'Free'
            or setup['binx'] != 2 or setup['biny'] != 2):
        raise ValueError('rapid archive bridge supports only Gr11/Gr13 Free, 2x2')
    base = Path(reference_root)/'archive/efosc'
    arcs = sorted((base/'arc'/setup['grism']/setup['filter']/setup['slit']).glob('*.fits'))
    if len(arcs) != 1:
        raise ValueError(f'exactly one reviewed archived arc required, found {len(arcs)}')
    candidates = []
    for p in sorted((base/'sens'/setup['grism']/setup['filter']).glob('*.fits')):
        sh = fits.getheader(p)
        if sh.get('MJD-OBS') is not None:
            candidates.append((abs(sh['MJD-OBS']-h['MJD-OBS']), p))
    candidates.sort()
    if not candidates or (len(candidates)>1 and candidates[0][0] == candidates[1][0]):
        raise ValueError('missing or tied archived sensitivity association')
    return arcs[0], candidates[0][1]


def extract_frame(frame, reference_root, output, hint, hint_info, waveair, arc_qa,
                  sensitivity, shift, sky_qa):
    import pypeit
    from pypeit.images.pypeitimage import PypeItImage
    from pypeit.slittrace import SlitTraceSet
    from pypeit.find_objects import FindObjects
    from pypeit.extraction import Extract
    from pypeit.specobjs import SpecObjs
    from pypeit.core.wave import airtovac, vactoair
    from .pypeit_adapter import EPESSTOEFOSC2Spectrograph

    if pypeit.__version__ != '1.14.0':
        raise ValueError('this runner is tested only with PypeIt 1.14.0')
    path = Path(frame['path'])
    h, setup = frame['metadata'], frame['setup']
    stem = science_stem(h['OBJECT'], h['DATE-OBS'], setup['grism'], setup['filter'], setup['slit'])
    registry = {p.name: fits.getheader(p).get('DATE-OBS') for p in (output/'products').glob('*_f.fits')}
    filename = product_name(stem, h['DATE-OBS'], registry, '_f')
    basename = filename[:-7]
    if (output/'products'/filename).exists():
        raise FileExistsError(f'product already exists: {filename}; use a fresh output directory')
    inst = EPESSTOEFOSC2Spectrograph()
    ny, nx = waveair.shape
    ymin = 4 if setup['grism']=='Gr11' else 0
    xlo, xhi = max(0,int(hint)-70), min(nx,int(hint)+71)
    with fits.open(path) as hdus:
        det = inst.get_detector_par(1,hdus)
        data = hdus[0].data[ymin:1015,99+xlo:99+xhi].astype(float)*h['ESO DET OUT1 GAIN']
    w = waveair[:,xlo:xhi]+shift
    tilts = (w-w.min())/(w.max()-w.min())
    par = inst.profile_parameters('rapid')
    par['flexure']['spec_method']='skip'  # already measured explicitly in air wavelengths
    par['reduce']['findobj']['maxnumber_sci']=3
    par['reduce']['findobj']['snr_thresh']=5
    par['reduce']['findobj']['skip_second_find']=True
    par['reduce']['skysub']['bspline_spacing']=1.0
    par['rdx']['redux_path']=str(output)
    rn = np.full(data.shape, h['ESO DET OUT1 RON']**2)
    sci = PypeItImage(data, ivar=1/(np.maximum(data,0)+rn), rn2img=rn, base_var=rn,
                     detector=det, exptime=h['EXPTIME'], noise_floor=0.,shot_noise=True,
                     bpm=~np.isfinite(data))
    sci.build_mask(saturation=det['saturation']*h['ESO DET OUT1 GAIN'],mincounts=-1e10)
    slits = SlitTraceSet(np.zeros(ny),np.full(ny,xhi-xlo-1.),'MultiSlit',
                        detname='DET01',nspat=xhi-xlo,PYP_SPEC=inst.name,binspec=2,binspat=2)
    finder = FindObjects.get_instance(sci,slits,inst,par,'science',tilts=tilts,
                                     show=False,basename=basename)
    sky, found = finder.run()
    from .sky_regions import capture_sky_selection
    sky_selection = capture_sky_selection(finder, found)
    candidates = [{'name':s.NAME,'trimmed_spatial_pixel':float(s.SPAT_PIXPOS+xlo)} for s in found]
    if len(found)==0:
        raise ValueError('no source detected in target window')
    distances = np.array([abs(s.SPAT_PIXPOS+xlo-hint) for s in found])
    order = np.argsort(distances)
    if distances[order[0]]>15 or (len(order)>1 and distances[order[1]]<15):
        raise ValueError(f'absent or ambiguous source at expected position {hint}: {candidates}')
    # Keep other detected sources in the sky/object model; export only the target.
    target_name = found[order[0]].NAME
    extractor = Extract.get_instance(sci,slits,found,inst,par,'science',global_sky=sky,
                    tilts=tilts,waveimg=airtovac(w*u.AA).value,show=False,basename=basename)
    result = extractor.run()
    extracted = result[4]
    selected = [i for i,s in enumerate(extracted) if s.NAME==target_name]
    if len(selected)!=1:
        raise ValueError('target lost during extraction')
    objects = extracted[np.array(selected)]
    s = objects[0]
    s.DETECTOR = det
    native = output/'native'/('spec1d_'+basename+'.fits')
    subheader = {k:h[k] for k in ('RA','DEC','EXPTIME','DATE-OBS','INSTRUME','MJD-OBS')}
    subheader.update({'TARGET':h['OBJECT'],'PYP_SPEC':inst.name,'PYPELINE':'MultiSlit',
                     'WAVEMED':'vacuum','SPECSYS':'TOPOCENT','EPSTATUS':'EXPERIMENTAL'})
    objects.write_to_fits(subheader,str(native),overwrite=False)
    check = SpecObjs.from_fitsfile(str(native))
    if len(check)!=1 or not np.array_equal(check[0].OPT_COUNTS,s.OPT_COUNTS):
        raise ValueError('native spectrum did not round-trip')
    np.savez_compressed(output/'native'/(basename+'_images.npz'),data=data,
        sky=result[0],object_model=result[1],ivar=result[2],mask=result[3].mask, waveair=w,
        trace=s.TRACE_SPAT,spatial_origin=xlo,raw_y_origin=ymin, **sky_selection)
    extinction = Path(reference_root)/'standard/extinction/extinction_lasilla.dat'
    wave = vactoair(s.OPT_WAVE*u.AA).value
    # Stay inside the archived reference-line bracket (shifted to this science exposure).
    low, high = np.min(arc_qa['reference_lines'])+shift, np.max(arc_qa['reference_lines'])+shift
    step = 5.5 if setup['grism']=='Gr13' else 4.0
    grid = np.arange(np.ceil(low/step)*step,high-step,step)
    bands, variances, masks = [],[],[]
    for kind in ('OPT','BOX'):
        kw = vactoair(s[kind+'_WAVE']*u.AA).value
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
    header['OBJECT']=h['OBJECT']; header['CRVAL1']=float(grid[0]); header['CRPIX1']=1.
    header['CD1_1']=step; header['CDELT1']=step; header['CTYPE1']='LINEAR'
    header['CUNIT1']='Angstrom'; header['WAVEMED']='air'; header['DC-FLAG']=0
    header['BUNIT']='erg / (s cm2 Angstrom)'; header['GRISM']=setup['grism']
    header['FILTER']=setup['filter'];header['SLIT']=setup['slit'];header['FILETYPE']=22208
    header['ARCFILE']=h['ARCFILE'];header['EXPTIME']=h['EXPTIME'];header['AIRMASS']=h['ESO TEL AIRM START']
    header['PROV1']=h['ARCFILE'];header['TRACE1']=native.name
    header['QUALITY']='Rapid';header['PYPEITV']=pypeit.__version__
    header['SENSFUN']=sensitivity.name;header['ARCREF']=Path(arc_qa['arc']).name
    header['WAVSHIFT']=shift;header['FLUXCAL']='ARCHIVE';header['TELLURIC']='NONE'
    header['BANDID1']='optimal flux';header['BANDID2']='boxcar flux'
    header['BANDID3']='sky flux in optimal aperture';header['BANDID4']='optimal flux uncertainty'
    center = float(np.nanmedian(s.TRACE_SPAT)+xlo)+1  # IRAF one-based aperture coordinates
    header['APNUM1']=f'1 1 {center-float(s.BOX_RADIUS):.3f} {center+float(s.BOX_RADIUS):.3f}'
    header['HISTORY']='Experimental archive bridge; PypeIt sky, trace, optimal and boxcar extraction.'
    header['HISTORY']='No bias/flat/dark/overscan or telluric correction. Not a certified ESO product.'
    header['HISTORY']='Bin-overlap resampling; propagated diagonal variance; covariance not stored.'
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
          'processing':{'trim_numpy_yx':[ymin,1015,99,950],
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
    if not qa['raw_unchanged']:
        raise ValueError('raw input changed during processing')
    (output/'qa'/(basename+'.json')).write_text(json.dumps(qa,indent=2,allow_nan=False)+'\n')
    return qa


def reduce_night(input_dir, output_dir, reference_root, *, targets=None, include_standards=False,
                 plot_python=None, skip_report=False):
    """Single-writer run with durable per-exposure results and explicit failures."""
    output = Path(output_dir).resolve()
    reference_root = Path(reference_root).resolve()
    if (output/'run.json').exists():
        raise FileExistsError('run.json exists; choose a new run directory to preserve source details')
    for sub in ('products','native','qa','QA/PNGs','source'):
        (output/sub).mkdir(parents=True,exist_ok=True)
    report = inventory([input_dir])
    if report['errors'] or report['identity_conflicts']:
        raise ValueError('resolve unreadable inputs or conflicting archive identities first')
    roles = {'science','standard_candidate'} if include_standards else {'science'}
    frames = [f for f in report['frames'] if f['role'] in roles and 'duplicate_of' not in f
              and (not targets or f['metadata']['OBJECT'] in targets)]
    if not frames:
        raise ValueError('no matching raw exposures')
    if any(f['issues'] for f in frames):
        raise ValueError('selected frames have invalid metadata')
    import pypeit
    import astropy
    import scipy
    source_hashes={}
    for p in sorted(Path(__file__).parent.glob('*.py')):
        source_hashes[p.name]=sha256(p)
        shutil.copyfile(p,output/'source'/p.name)
    run = {'schema_version':1,'status':'EXPERIMENTAL','method':'archive_calibration_bridge_with_native_PypeIt_extraction',
           'input_dir':str(Path(input_dir).resolve()),'output_dir':str(output),
           'python':sys.executable,'pypeit_version':pypeit.__version__,'numpy_version':np.__version__,
           'python_version':sys.version.split()[0], 'astropy_version':astropy.__version__,
           'scipy_version':scipy.__version__, 'source_sha256':source_hashes,
           'limitations':['No raw arc, bias or flat calibration in this demonstration.',
                         'Archived IRAF line positions and sensitivity are imported; not native PypeIt calibration generation.',
                         'No telluric correction; absolute flux and red second-order contamination are unvalidated.',
                         'Red fringing remains because rapid processing applies no flat correction.',
                         'Source positions without a historical aperture remain unverified.',
                         'Resampling covariance is not stored; output uncertainty is diagonal only.'],
           'results':[],'errors':[],'skipped':[]}
    cache = {}
    for f in sorted(frames,key=lambda f:f['metadata']['MJD-OBS']):
        try:
            if f['setup']['grism'] not in {'Gr11','Gr13'}:
                run['skipped'].append({'path':f['path'],'reason':'grism outside demonstrated archive bridge'})
                continue
            arc,sens = select_archive(f,reference_root)
            if str(arc) not in cache:
                cache[str(arc)]=fit_arc(arc)
            wave,arcqa=cache[str(arc)]
            raw = fits.getdata(f['path']).astype(float)
            ymin=4 if f['setup']['grism']=='Gr11' else 0
            data=raw[ymin:1015,99:950]
            if data.shape!=wave.shape:
                raise ValueError('archived arc and trimmed science geometry disagree')
            shift,skyqa=sky_flexure(data,wave)
            hint,hintinfo=target_hint(f,input_dir)
            print(f"Reducing {f['metadata']['OBJECT']} {f['setup']['grism']}: shift {shift:.3f} A",file=sys.stderr,flush=True)
            qa=extract_frame(f,reference_root,output,hint,hintinfo,wave,arcqa,sens,shift,skyqa)
            run['results'].append(qa)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            run['errors'].append({'path':f['path'],'object':f['metadata']['OBJECT'],'error':str(exc)})
        finally:
            (output/'run.json').write_text(json.dumps(run,indent=2,allow_nan=False)+'\n')
    if not skip_report:
        from .report import build_report
        try:
            run['report'] = build_report(output, plot_python=plot_python)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            run['report'] = {'status': 'incomplete', 'generation_error': str(exc)}
        (output/'run.json').write_text(json.dumps(run, indent=2, allow_nan=False)+'\n')
    return run
