"""Audit orchestration uses synthetic files, never observing data or services."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from efospec.calibration_audit import audit, standard_sky
from efospec.inventory import sha256


@pytest.fixture
def saved_audit(tmp_path, monkeypatch):
    from pypeit.specobjs import SpecObjs
    from efospec import native_acceptance, standard_reference
    root = tmp_path / 'inputs'
    root.mkdir()
    def file(name, contents):
        p = root / name
        p.write_bytes(contents)
        return p
    physical = file('reference.dat', b'physical reference')
    extinction = file('extinction.dat', b'extinction')
    wave = np.arange(4500., 8500., 5.)
    standards = []
    for index, (filt, minute) in enumerate([('Free', 0), ('Free', 10), ('GG495', 5)]):
        raw = file(f'raw-{index}.fits', str(index).encode())
        spectrum = file(f'spec1d-{index}.fits', b'saved spectrum')
        response = root / f'response-{index}.fits'
        zp = np.full(wave.size, 20. if filt == 'Free' else 19.)
        fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns([
            fits.Column(name='WAVE', format='D', array=wave),
            fits.Column(name='ZEROPOINT', format='D', array=zp),
            fits.Column(name='VALID', format='L', array=np.ones(wave.size, bool)),
        ], name='RESPONSE')]).writeto(response, checksum=True)
        cal = root / f'cal-{index}'
        cal.mkdir()
        (cal / 'wavelength-map.npz').write_bytes(b'protected map')
        (cal / 'master.fits').write_bytes(b'protected master')
        manifest = {'raw_inputs': {str(raw): sha256(raw)},
                    'processed_files': {'master.fits': sha256(cal / 'master.fits')},
                    'wavelength_map_sha256': sha256(cal / 'wavelength-map.npz')}
        (cal / 'calibration.json').write_text(json.dumps(manifest))
        standards.append({'frame': {'path': str(raw), 'sha256': sha256(raw), 'night': '2024-11-14',
            'setup': dict(grism='Gr13', filter=filt, slit='slit1.0', binx=2, biny=2, readout='normal'),
            'metadata': {'OBJECT': 'standard', 'EXPTIME': 60., 'ESO TEL AIRM START': 1.1,
                         'MJD-OBS': 60629. + minute / 1440}},
            'counts': {'native_spec1d': str(spectrum), 'product_sha256': {str(spectrum): sha256(spectrum)},
                       'calibration_directory': str(cal), 'calibration_manifest_sha256': sha256(cal / 'calibration.json')},
            'fit': {'status': 'response_built_unvalidated', 'response': {
                'path': str(response), 'sha256': sha256(response), 'reference_file': str(physical),
                'reference_details': {'reference_sha256': sha256(physical)},
                'extinction': {'path': str(extinction), 'sha256': sha256(extinction)}}}})
    run = root / 'run.json'
    record = {'night': '2024-11-14', 'standards': standards}
    run.write_text(json.dumps(record))
    monkeypatch.setattr(SpecObjs, 'from_fitsfile', lambda *a, **k: [object()])
    monkeypatch.setattr(standard_reference, 'standard_reference', lambda *a, **k: {'cal_file': str(physical)})
    def recovery(frame, obj, response, reference):
        return {'status': 'diagnostic', 'raw': frame['path']}, {
            'waveair': wave, 'ratio': np.ones(wave.size), 'valid': np.ones(wave.size, bool)}
    monkeypatch.setattr(native_acceptance, 'standard_recovery', recovery)
    return SimpleNamespace(root=root, run=run, record=record, standards=standards,
                           physical=physical, output=tmp_path / 'audit')


def test_audit_keeps_trials_separate_and_protects_all_inputs(saved_audit):
    s = saved_audit
    before = {p: sha256(p) for p in s.root.rglob('*') if p.is_file()}
    result = audit(s.run, s.output, night='2024-11-14')
    assert result['status'] == 'complete' and result['protected_inputs_unchanged']
    assert not result['science_products_modified'] and not result['absolute_flux_validated']
    assert len(result['standard_checks']) == 3
    assert len(result['transfers']) == 2  # Free-to-Free only, never self-transfer.
    assert len(result['paired_response_trials']) == 2
    for trial in result['paired_response_trials']:
        response = trial['response']
        assert not response['trial']['approved_for_science']
        assert len(trial['held_out']) == 1
        with fits.open(response['path']) as hdus:
            assert hdus[0].header['EPEXPER']
            assert all(h.verify_checksum() == 1 for h in hdus)
            np.testing.assert_allclose(hdus['RESPONSE'].data['ZEROPOINT'], 20.)
    assert before == {p: sha256(p) for p in before}
    assert json.loads((s.output / 'audit.json').read_text())['status'] == 'complete'
    with pytest.raises(FileExistsError):
        audit(s.run, s.output, night='2024-11-14')


@pytest.mark.parametrize('problem', ['wrong-night', 'no-responses', 'missing-reference', 'changed-reference', 'changed-master'])
def test_audit_fails_closed_on_invalid_saved_inputs(saved_audit, problem):
    s = saved_audit
    night = '2024-11-14'
    if problem == 'wrong-night': night = '2024-11-15'
    elif problem == 'no-responses': s.record['standards'] = []
    elif problem == 'missing-reference': s.physical.unlink()
    elif problem == 'changed-reference': s.physical.write_bytes(b'changed')
    else: (s.root / 'cal-0/master.fits').write_bytes(b'changed')
    s.run.write_text(json.dumps(s.record))
    with pytest.raises(ValueError): audit(s.run, s.output, night=night)
    assert not (s.output / 'audit.json').exists()


def test_audit_rejects_equal_time_filter_pairs(saved_audit):
    from copy import deepcopy
    s = saved_audit
    duplicate = deepcopy(s.standards[2])
    # Two independently named candidates at the same time are ambiguous.
    duplicate['frame']['path'] = str(s.root / 'other-filtered.fits')
    Path(duplicate['frame']['path']).write_bytes(b'independent filtered exposure')
    duplicate['frame']['sha256'] = sha256(Path(duplicate['frame']['path']))
    s.record['standards'].append(duplicate)
    s.run.write_text(json.dumps(s.record))
    with pytest.raises(ValueError, match='ambiguous paired-filter'):
        audit(s.run, s.output, night='2024-11-14')
    assert not list(s.output.glob('paired-response-*.fits'))


def test_audit_detects_input_mutation_during_measurement(saved_audit, monkeypatch):
    from efospec import native_acceptance
    s = saved_audit
    original = native_acceptance.standard_recovery
    def changed(*args, **kwargs):
        (s.root / 'cal-0/master.fits').write_bytes(b'mutated during measurement')
        return original(*args, **kwargs)
    monkeypatch.setattr(native_acceptance, 'standard_recovery', changed)
    with pytest.raises(ValueError, match='modified a protected input'):
        audit(s.run, s.output, night='2024-11-14')
    assert json.loads((s.output / 'audit.json').read_text())['status'] == 'running'


def test_standard_sky_excludes_trace_and_detector_masks(tmp_path, monkeypatch):
    from efospec import native_calibrations, native_sky
    images = tmp_path / 'images.npz'
    np.savez(images, raw_y_origin=2, data=np.zeros((6, 100)))
    wave = np.broadcast_to(np.arange(10)[:, None] + 6000., (10, 100)).copy()
    bad = np.zeros(wave.shape, bool); bad[:, 20] = True
    bundle = {'slitmask': np.zeros(wave.shape, int), 'wavevac': wave}
    image = SimpleNamespace(image=np.ones(wave.shape), fullmask=SimpleNamespace(flagged=lambda: bad), detector={'platescale': .25})
    monkeypatch.setattr(native_calibrations, 'load_calibrations', lambda path: bundle)
    monkeypatch.setattr(native_calibrations, 'process_exposure', lambda f, b: image)
    def measure(data, air, **kw):
        assert data.shape == (6, 80)
        assert kw['required'] is False and kw['slit_width_pixels'] == 2.
        assert not kw['good_pixels'][:, 10].any()  # bad detector column 20
        assert not kw['good_pixels'][:, 10:71].any()  # source +/- 30 pixels
        assert kw['good_pixels'][:, :10].all()
        assert (air < 6008).all()  # vacuum-to-air conversion occurred
        return -2., {'held_out_6363_pass': True}
    monkeypatch.setattr(native_sky, 'exposure_flexure', measure)
    entry = {'frame': {'setup': {'grism': 'Gr13', 'slit': 'slit1.0', 'binx': 2}},
             'counts': {'calibration_directory': tmp_path, 'images': images, 'median_trace_raw_pixel': 50.}}
    result = standard_sky(entry)
    assert result['candidate_shift_angstrom'] == -2.
    assert result['applied_shift_angstrom'] is None and result['review_only']
    entry['frame']['setup']['grism'] = 'Gr16'
    assert standard_sky(entry)['status'] == 'not_tested'
