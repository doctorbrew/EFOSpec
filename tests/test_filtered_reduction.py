from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from efospec.filtered_reduction import supported_counts, free_comparisons, fit_standard_response
from test_planning import frame, report
from test_native_end_to_end import synthetic_raw_night


def counts():
    from pypeit.specobj import SpecObj
    from pypeit.specobjs import SpecObjs
    s = SpecObj('MultiSlit', 'DET01', SLITID=0)
    for kind in ('OPT', 'BOX'):
        for name, values in [('WAVE', np.linspace(4000., 9500., 600)),
                             ('COUNTS', np.arange(600.)-10), ('COUNTS_IVAR', np.ones(600)),
                             ('MASK', np.ones(600, bool))]:
            setattr(s, kind+'_'+name, values)
    return SpecObjs(np.array([s], dtype=object))


def test_count_support_masks_extrapolation_without_changing_values():
    original = counts()
    original[0].OPT_COUNTS[150] = -5.
    original[0].OPT_COUNTS_IVAR[300] = 0.
    result = supported_counts(original, [5000., 9000.])[0]
    assert not result.OPT_MASK[0] and not result.OPT_MASK[-1] and not result.OPT_MASK[300]
    assert result.OPT_MASK[150] and result.OPT_COUNTS[150] == -5.
    np.testing.assert_array_equal(result.OPT_COUNTS, original[0].OPT_COUNTS)
    assert original[0].OPT_MASK.all()
    with pytest.raises(ValueError, match='insufficient'):
        supported_counts(original, [8000., 8100.])


def test_free_comparisons_preserve_candidates_without_crossing_setup_or_night():
    target = frame('VMa2', 'standard_candidate')
    target['setup']['filter'] = 'GG495'
    free = deepcopy(target); free['path'] = '/free.fits'; free['setup']['filter'] = 'Free'
    wrong_slit = deepcopy(free); wrong_slit['setup']['slit'] = 'slit1.5'
    wrong_night = deepcopy(free); wrong_night['night'] = '20241115'
    result = free_comparisons(target, [wrong_slit, wrong_night, free])
    assert len(result) == 1 and result[0]['path'] == '/free.fits'
    assert not result[0]['identity_verified']


def test_missing_reference_records_failure_without_modifying_counts(tmp_path, monkeypatch):
    def unavailable(*args): raise ValueError('no physical reference')
    monkeypatch.setattr('efospec.standard_reference.standard_reference', unavailable)
    original = counts()
    result = fit_standard_response(frame(), original, tmp_path)
    assert result['status'] == 'reference_unavailable'
    assert result['error'] == 'no physical reference'
    assert not result['independent_flux_validation']
    assert original[0].OPT_MASK.all()


def test_red_science_is_explicitly_review_counts_not_flux(tmp_path, monkeypatch):
    from efospec import filtered_reduction as module
    target = frame('AT2026twd', 'science')
    target['setup'].update(grism='Gr16', filter='OG530')
    monkeypatch.setattr(module, 'inventory', lambda paths: report([target]))
    monkeypatch.setattr(module, 'validate_associations', lambda *a: None)
    def prepare(target, associations, directory, position, **kwargs):
        assert kwargs['red_counts_only'] and kwargs['arc_supported_only']
        return {'bundle': {'directory':directory/'calibration'}}
    monkeypatch.setattr(module, 'prepare', prepare)
    monkeypatch.setattr(module, 'export_counts', lambda *a: ({'object':'AT2026twd',
        'flux_calibrated':False, 'science_validated':False}, counts()))
    monkeypatch.setattr(module, 'sha256', lambda p: p.stem)
    def no_response(*args): raise AssertionError('science is not a response standard')
    monkeypatch.setattr(module, 'fit_standard_response', no_response)
    result = module.reduce_red_night('/unused', tmp_path/'out', night='2024-11-14')
    assert result['status'] == 'complete'
    assert not result['accepted_science_delivery'] and not result['science_validated']
    assert result['results'][0]['flux_response']['status'] == 'not_applied'


def test_wrong_night_is_rejected_before_creating_outputs(tmp_path, monkeypatch):
    from efospec.filtered_reduction import reduce_filtered_night
    target = frame('std', 'standard_candidate'); target['setup']['filter'] = 'GG495'
    monkeypatch.setattr('efospec.filtered_reduction.inventory', lambda paths: report([target]))
    with pytest.raises(ValueError, match='single requested'):
        reduce_filtered_night('/unused', tmp_path/'output', night='2026-10-29', render_report=False)
    assert not (tmp_path/'output').exists()


def test_failed_extraction_keeps_completed_standard_and_cannot_overwrite(tmp_path, monkeypatch):
    from efospec import filtered_reduction as module
    first, second = frame('one', 'standard_candidate'), frame('two', 'standard_candidate')
    for target in (first, second): target['setup']['filter'] = 'GG495'
    monkeypatch.setattr(module, 'inventory', lambda paths: report([first, second]))
    monkeypatch.setattr(module, 'validate_associations', lambda *a: None)
    def prepare(target, associations, directory, position, cached=None, **kwargs):
        if target == second: raise ValueError('background did not converge')
        return {'bundle': {'directory': directory/'calibration'}}
    monkeypatch.setattr(module, 'prepare', prepare)
    monkeypatch.setattr(module, 'export_counts', lambda *a: ({'object': 'one'}, counts()))
    monkeypatch.setattr(module, 'sha256', lambda path: path.stem)
    monkeypatch.setattr(module, 'fit_standard_response', lambda *a: {'status': 'reference_unavailable'})
    result = module.reduce_filtered_night('/unused', tmp_path/'output', night='2024-11-14', render_report=False)
    saved = json.loads((tmp_path/'output/run.json').read_text())
    assert saved['status'] == 'partial' and len(saved['results']) == 1 and len(saved['errors']) == 1
    assert saved['errors'][0]['error'] == 'background did not converge'
    assert not result['second_order_correction_applied']
    with pytest.raises(FileExistsError):
        module.reduce_filtered_night('/unused', tmp_path/'output', night='2024-11-14', render_report=False)


def test_arc_supported_crop_accounts_for_spatial_wavelength_tilt():
    from efospec.native_reduction import arc_supported_rows
    wave = np.arange(4000., 9500., 5.)[:, None]+np.array([0., 12.])[None, :]
    first, last = arc_supported_rows(wave, [5000., 9000.])
    assert first == 200 and last == 998
    assert np.all((wave[first:last] >= 5000) & (wave[first:last] <= 9000))
    with pytest.raises(ValueError, match='insufficient contiguous'):
        arc_supported_rows(wave, [5000., 5100.])


def test_reviewed_background_requires_same_raw_calibration_crop_and_pixels(tmp_path):
    from efospec.filtered_background import load_background_reviews, review_arguments
    from efospec.inventory import sha256
    raw=tmp_path/'standard.fits'; raw.write_bytes(b'raw')
    manifest=tmp_path/'run.json'; manifest.write_text('{}')
    calibration=tmp_path/'calibration'; calibration.mkdir()
    (calibration/'calibration.json').write_text('{}')
    data=np.zeros((120,201)); wave=np.broadcast_to(np.linspace(5000.,9000.,120)[:,None], data.shape).copy()
    images=tmp_path/'images.npz'
    np.savez(images,data=data,waveair=wave,found_traces=np.array([np.full(120,100.),np.full(120,135.)]))
    hashes={'raw':sha256(raw),'images':sha256(images),'manifest':sha256(manifest)}
    recipe={'schema_version':1,'engine_version':'3.0.0','coordinates':'raw_detector_pixels_zero_based',
        'input_sha256':hashes,'source_mode':'manual',
        'objects':[{'id':'primary','label':'standard','kind':'point','spec':310.,'spat':548.,'fwhm':4.,'radius':7.}],
        'sky':{'mode':'pypeit_local','include':[[500,530],[600,630]],'exclude':[],'degree':2,'sigma_clip':4.}}
    path=tmp_path/'recipe.json';path.write_text(json.dumps(recipe))
    review={'raw_name':raw.name,'raw_sha256':hashes['raw'],'manifest':str(manifest),'manifest_sha256':hashes['manifest'],
        'images':str(images),'images_sha256':hashes['images'],'recipe':str(path),'recipe_sha256':sha256(path),
        'raw_origin_yx':[250,448],'calibration_sha256':sha256(calibration/'calibration.json'),
        'reviewer':'test','evidence':'two clean finite bands'}
    document=tmp_path/'reviews.json';document.write_text(json.dumps({'schema_version':1,'reviews':[review]}))
    target={'path':str(raw),'sha256':hashes['raw']}
    loaded=load_background_reviews(document,[target])[raw.name]
    arguments,evidence=review_arguments(loaded,target,data,wave,(250,448),calibration)
    assert np.all(arguments['sky_input_mask'].sum(axis=1)==60)
    assert arguments['sky_model']=={'degree':2,'sigma_clip':4.}
    assert evidence['selection']=='explicit_two_sided_bands'
    with pytest.raises(ValueError,match='pixels or wavelengths differ'):
        review_arguments(loaded,target,data+1,wave,(250,448),calibration)
    with pytest.raises(ValueError,match='crop changed'):
        review_arguments(loaded,target,data,wave,(251,448),calibration)
    (calibration/'calibration.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='raw/calibration identity changed'):
        review_arguments(loaded,target,data,wave,(250,448),calibration)
    path.write_text('{}')
    with pytest.raises(ValueError,match='input changed: recipe'):
        review_arguments(loaded,target,data,wave,(250,448),calibration)


def test_filtered_photons_to_counts_response_and_portable_report(synthetic_raw_night, tmp_path, monkeypatch):
    import base64
    import re
    import shutil
    from astropy import units as u
    from astropy.io import fits
    from pypeit.specobjs import SpecObjs
    from efospec.filtered_reduction import reduce_filtered_night
    from efospec.inventory import inspect_file, sha256
    from efospec.epoch_report import build_filtered_page
    source, _, _ = synthetic_raw_night
    raw = tmp_path/'raw'; raw.mkdir()
    for path in source.glob('*.fits'):
        dest = raw/path.name; shutil.copyfile(path, dest)
        with fits.open(dest, mode='update') as hdus:
            hdus[0].header['HIERARCH ESO INS FILT1 NAME'] = 'GG495'
    wave = np.arange(3000., 11001., 2.)
    def physical(frame, cache):
        return dict(name='SyntheticStandard', std_ra=0., std_dec=0., cal_file='synthetic-truth',
                    std_source='test_photons', wave=wave*u.AA,
                    flux=np.full(wave.shape, 1000.)*u.erg/u.s/u.cm**2/u.AA)
    monkeypatch.setattr('efospec.standard_reference.standard_reference', physical)
    hashes = {path: sha256(path) for path in raw.glob('*.fits')}
    compact = inspect_file(raw/'standard.fits')['night']
    night = f'{compact[:4]}-{compact[4:6]}-{compact[6:]}'
    from efospec.__main__ import main
    assert main(['reduce-filtered',str(raw),'--night',night,'--output',str(tmp_path/'output')]) == 0
    result = json.loads((tmp_path/'output/run.json').read_text())
    assert result['status'] == 'complete' and not result['errors']
    assert result['report']['status'] == 'complete'
    assert len(result['results']) == 1
    row = result['results'][0]
    s = SpecObjs.from_fitsfile(row['native_spec1d'])[0]
    assert np.median(s.OPT_COUNTS[s.OPT_MASK]) == pytest.approx(20000., rel=.04)
    lo, hi = row['wavelength']['valid_wave_vacuum_angstrom']
    assert np.all((s.OPT_WAVE[s.OPT_MASK] >= lo) & (s.OPT_WAVE[s.OPT_MASK] <= hi))
    assert row['background']['minimum_side_samples'] >= 5
    assert row['background']['pypeit_exit_status'] == 0
    assert row['flux_response']['status'] == 'response_built_unvalidated'
    assert not row['flux_response']['training_closure']['independent_exposure']
    assert not row['flux_calibrated'] and not row['science_validated']
    assert all(sha256(path) == digest for path, digest in hashes.items())
    with fits.open(row['product'], checksum=True) as hdus:
        assert hdus[0].header['FLUXCAL'] == 'NONE'
        assert hdus[0].header['WAVEMED'] == 'vacuum'
        assert hdus['COUNTS'].columns['OPT_COUNTS'].unit == 'electron'
        np.testing.assert_array_equal(hdus['COUNTS'].data['OPT_VALID'], s.OPT_MASK)
        assert all(hdu.verify_checksum() == 1 for hdu in hdus)
    html = Path(result['report']['path']).read_text()
    assert 'ePESSTO+ / EFOSpec' in html and 'no independent flux validation' in html
    downloads = dict(re.findall(r'<a download="([^"]+)" href="data:[^,]+,([^"]+)">', html))
    assert base64.b64decode(downloads[Path(row['product']).name]) == Path(row['product']).read_bytes()
    assert base64.b64decode(downloads['run.json']) == (tmp_path/'output/run.json').read_bytes()
    for kind in ('counts', 'science', 'traces', 'profiles'):
        assert list((Path(row['product']).parent.parent/'plots').glob('FitQC_*_'+kind+'.pdf'))
    Path(row['product']).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='product changed'):
        build_filtered_page(tmp_path/'output')
