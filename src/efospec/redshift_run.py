"""One-night redshift evidence with independent NED and spectral measurements."""
from pathlib import Path
from .native_sky import wavelength_accepted
import json
import warnings

import numpy as np
from astropy.io import fits
from astropy.coordinates import SkyCoord,EarthLocation
from astropy.time import Time
from astropy import units as u

from .inventory import sha256
from .native_calibration import save_json
from .host_redshift import extract_2d_line_spectrum,measure_redshift,spatial_line_check


def ned_candidate(header,directory):
    from .field_catalogues import fetch_catalogue
    query=fetch_catalogue('NED',[float(header['RA']),float(header['DEC'])],.5,directory,timeout=20)
    centre=SkyCoord(header['RA']*u.deg,header['DEC']*u.deg,frame='fk5',equinox='J2000').icrs
    rows=[]
    for source in query['rows']:
        if not source['galaxy_candidate']:continue
        separation=float(centre.separation(SkyCoord(source['ra']*u.deg,source['dec']*u.deg)).arcsec)
        if separation<=30:rows.append(dict(source,separation_arcsec=separation))
    rows.sort(key=lambda r:r['separation_arcsec'])
    return dict(status=query['status'],candidate=rows[0] if rows else None,candidates=rows,
        association='nearest catalogue galaxy within 30 arcsec of header pointing; not a confirmed host',
        query_file=str(directory/'NED.json'),query_sha256=sha256(directory/'NED.json'),
        reference_frame='heliocentric',coordinate_basis='science header RA/DEC; no slit-to-sky registration')


def heliocentric(z,header,error=None):
    from astropy.utils import iers
    iers.conf.auto_download=False
    coord=SkyCoord(header['RA']*u.deg,header['DEC']*u.deg,frame='fk5',equinox='J2000').icrs
    location=EarthLocation.from_geodetic(header['ESO TEL GEOLON']*u.deg,header['ESO TEL GEOLAT']*u.deg,
                                        header['ESO TEL GEOELEV']*u.m)
    time=Time(header['MJD-OBS']+header['EXPTIME']/2/86400,format='mjd',scale='utc')
    with warnings.catch_warnings(record=True) as captured:
        correction=coord.radial_velocity_correction(kind='heliocentric',obstime=time,location=location).to_value(u.km/u.s)
    factor=1+correction/299792.458
    converted=dict(z_heliocentric=float((1+z)*factor-1),
        correction_km_s=float(correction),mid_exposure_mjd=float(time.mjd),
        warnings=[str(w.message) for w in captured],method='Astropy heliocentric optical correction; multiplicative in 1+z')
    # The correction is multiplicative in 1+z, so the line-fit error scales with
    # the same factor. The correction's own error is far below it and omitted.
    if error is not None:
        converted['z_heliocentric_error']=float(error*factor)
    return converted


def measure_night(night,output,*,project_root='.',rescue=None):
    from .run_record import snapshot_sources
    root=Path(project_root).resolve()/'runs'/night
    pointer=json.loads((root/'nightly/current.json').read_text())
    if pointer['night']!=night:raise ValueError('night mismatch')
    parent=root/'nightly'/pointer['revision']/'reduction';run=json.loads((parent/'run.json').read_text())
    from .manual_recovery_report import selected_manual_recoveries
    manuals=selected_manual_recoveries(parent)
    runs=[(parent,run)]+manuals
    automatic_rescue=rescue is None;excluded_rescue=None
    if rescue is None and (root/'rescue/current.json').exists():
        saved=json.loads((root/'rescue/current.json').read_text())
        rescue=(root/saved['path']).resolve()
        if saved['night']!=night or not rescue.is_relative_to(root/'rescue') or sha256(rescue/'run.json')!=saved['run_sha256']:
            raise ValueError('invalid current rescue pointer')
    if rescue:
        rescue=Path(rescue).resolve();extra=json.loads((rescue/'run.json').read_text())
        if extra['night']!=night or extra['parent_sha256']!=sha256(parent/'run.json'):
            if not automatic_rescue:raise ValueError('rescue parent mismatch')
            excluded_rescue=dict(path=str(rescue),reason='previous reduction revision');rescue=None
        else:runs.append((rescue,extra))
    from .redshift_report import evidence_inside_night
    output=Path(output).resolve()
    if not evidence_inside_night(output,root):raise ValueError('redshift evidence must stay inside dated QC')
    output.mkdir(parents=True,exist_ok=False)
    manifest=dict(night=night,excluded_rescue=excluded_rescue,method='independent_2d_emission_line_redshifts',status='running',results=[],errors=[],
        parent_run_sha256={str(p/'run.json'):sha256(p/'run.json') for p,_ in runs},source_sha256=snapshot_sources(output),
        limitations=['Automatic line-system candidates, not confirmed hosts.','No NED prior enters spectral fitting.','Formal errors exclude wavelength, background and resampling systematics.','Search covers -0.003 <= z <= 1 and optical emission lines; absorption-only galaxies may have no estimate.'])
    save_json(output/'redshifts.json',manifest)
    for folder,source in runs:
        for result in source['results']:
            if result.get('role')!='science':continue
            directory=output/Path(result['raw']).stem;directory.mkdir()
            try:
                if sha256(Path(result['raw']))!=result['raw_sha256']:raise ValueError('raw exposure changed')
                image=Path(result['native_spec1d']).parent/(Path(result['product']).name[:-7]+'_images.npz')
                if sha256(image)!=result['images_sha256']:raise ValueError('native images changed')
                with np.load(image) as a:arrays={k:a[k] for k in a.files}
                extracted=extract_2d_line_spectrum(arrays)
                fwhm={'Gr11':18.,'Gr13':35.}[result['grism']]
                spectral=measure_redshift(extracted['wave_vacuum'],extracted['counts'],extracted['sigma'],fwhm=fwhm)
                if spectral['solutions']:
                    spatial=spatial_line_check(extracted,spectral['solutions'][0],fwhm)
                    spectral['spatial_validation']=spatial
                    if spectral['z'] is not None and not spatial['passed']:
                        spectral.update(status='spatially_inconsistent',z=None)
                header=fits.getheader(result['raw'])
                wavelength_validated=wavelength_accepted(result['sky_flexure'])
                spectral['wavelength_validated']=wavelength_validated
                spectral['wavelength_acceptance_policy']=result['sky_flexure'].get('validation_policy','three-line')
                spectral['diagnostic_6363_error']=result['sky_flexure'].get('diagnostic_6363_error')
                spectral['method_parameters']=dict(nominal_fwhm_angstrom=fwhm,aperture_radius_pixels=20.,
                    minimum_independent_groups=3,minimum_line_snr=5.,minimum_delta_chi2=30.,
                    search_range=[-.003,1.],redshift_error='fit covariance with unresolved-blend centroid floors; excludes wavelength and background systematics')
                spectral['wavelength_systematic_error']=None
                spectral['wavelength_warning']='unknown wavelength systematic error' if not wavelength_validated else 'sky check passed; full calibration covariance unavailable'
                if spectral['z'] is not None:
                    spectral.update(heliocentric(spectral['z'],header,
                                                 spectral['solutions'][0].get('z_error')))
                    spectral['status']='candidate' if wavelength_validated else 'provisional_wavelength'
                record=dict(object=result['object'],raw=result['raw'],raw_sha256=result['raw_sha256'],
                    product=result['product'],product_sha256=sha256(Path(result['product'])),
                    images=str(image),images_sha256=sha256(image),spectral=spectral,
                    ned=ned_candidate(header,directory/'catalogue'),reference_frame='heliocentric',
                    input_wavelength_medium='air',fit_wavelength_medium='vacuum',host_identified=False)
                np.savez_compressed(directory/'line-spectrum.npz',**extracted)
                record['diagnostic_arrays']=str(directory/'line-spectrum.npz')
                record['diagnostic_arrays_sha256']=sha256(directory/'line-spectrum.npz')
                from .redshift_plots import plot_redshift
                record['figures']=plot_redshift(record,extracted,directory)
                path=directory/'redshift.json';save_json(path,record)
                manifest['results'].append(dict(object=result['object'],raw=result['raw'],path=str(path),sha256=sha256(path)))
                print(result['object'],spectral['status'],spectral.get('z_heliocentric'),flush=True)
            except Exception as exc:
                import traceback
                (directory/'error.log').write_text(traceback.format_exc())
                manifest['errors'].append(dict(object=result['object'],raw=result['raw'],error=str(exc)))
                print('ERROR',result['object'],str(exc),flush=True)
            save_json(output/'redshifts.json',manifest)
    manifest['status']='partial' if manifest['errors'] else 'complete';save_json(output/'redshifts.json',manifest)
    return manifest


def activate_measurements(directory, *, project_root='.'):
    """Publish a completed measurement revision into the same-night report."""
    from datetime import datetime,timezone
    from shutil import copy2
    from .epoch_report import EpochPage,build_epoch_page
    from .redshift_report import load_redshifts
    directory=Path(directory).resolve();path=directory/'redshifts.json'
    manifest=json.loads(path.read_text());root=Path(project_root).resolve()/'runs'/manifest['night']
    from .redshift_report import evidence_inside_night
    if not evidence_inside_night(directory,root):raise ValueError('redshift evidence outside dated QC')
    if manifest['status']!='complete':raise ValueError('redshift run must complete before promotion')
    current=json.loads((root/'nightly/current.json').read_text())
    parent=root/'nightly'/current['revision']/'reduction';rescue=None
    if (root/'rescue/current.json').exists():
        saved=json.loads((root/'rescue/current.json').read_text());rescue=(root/saved['path']).resolve()
        if sha256(rescue/'run.json')!=saved['run_sha256']:raise ValueError('rescue pointer changed')
        extra=json.loads((rescue/'run.json').read_text())
        if extra.get('parent_sha256')!=sha256(parent/'run.json'):rescue=None
    from .manual_recovery_report import selected_manual_recoveries
    manuals=[p for p,_ in selected_manual_recoveries(parent)]
    expected={str(p/'run.json'):sha256(p/'run.json') for p in [parent,rescue]+manuals if p is not None}
    if manifest['parent_run_sha256']!=expected:raise ValueError('measurements do not match current accepted/rescue reductions')
    pointer=root/'QC/redshift-current.json';previous=pointer.read_bytes() if pointer.exists() else None
    archive=directory/'previous-report'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-redshift-update')
    archive.mkdir(parents=True,exist_ok=False)
    if previous is not None:copy2(pointer,archive/pointer.name)
    if (root/'index.html').exists():
        portable=root/'index-portable.html'
        if portable.exists() and 'data-report-assets="local"' in (root/'index.html').read_text():
            # An archived compact page would resolve assets relative to the
            # archive folder. Preserve its self-contained counterpart as index.
            copy2(root/'index.html',archive/'index-local.html')
            copy2(portable,archive/'index.html')
        else:copy2(root/'index.html',archive/'index.html')
    try:
        save_json(pointer,dict(night=manifest['night'],path=str(path.relative_to(root)),sha256=sha256(path)))
        # Fail closed on changed products, plots or provenance before rendering.
        load_redshifts(EpochPage(root),parent,rescue,manuals=manuals)
        return build_epoch_page(manifest['night'],project_root)
    except Exception:
        if previous is None:pointer.unlink(missing_ok=True)
        else:pointer.write_bytes(previous)
        raise
