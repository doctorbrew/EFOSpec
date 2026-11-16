"""Sky acceptance must remeasure the corrected grid and preserve masked gaps."""
from types import SimpleNamespace

import numpy as np
import pytest

from efospec import sky_comparison as sky
from efospec.native_sky import SkyValidationError


@pytest.fixture
def grid():
    wave = np.broadcast_to(np.linspace(5400., 8500., 300)[:, None], (300, 12)).copy()
    data = np.broadcast_to((10. + np.sin(np.arange(300) / 5.))[:, None], wave.shape).copy()
    good = np.ones(data.shape, bool)
    good[100:110] = False
    data[100:110] = 1e9
    return data, wave, good


@pytest.fixture
def template_path(tmp_path, monkeypatch):
    from pypeit import dataPaths
    path = tmp_path / 'sky.fits'; path.write_bytes(b'synthetic reference provenance')
    monkeypatch.setattr(type(dataPaths.sky_spec), 'get_file_path', lambda *a, **k: path)
    return path


def test_comparison_preserves_gaps_and_does_not_apply_shift(grid, template_path, monkeypatch):
    from pypeit.core import flexure
    captured = []
    results = []
    def correlate(spectrum, **kwargs):
        captured.append(spectrum)
        x = np.arange(100.)
        flux = np.exp(-.5*((x-35)/2)**2) + .7*np.exp(-.5*((x-65)/3)**2)
        result = {'shift': 0., 'corr': np.ones(5), 'subpix': np.arange(5.), 'corr_cen': 2.,
                  'sky_spec': SimpleNamespace(wave=x, flux=flux),
                  'arx_spec': SimpleNamespace(flux=flux.copy()), 'polyfit': SimpleNamespace(fitc=np.array([1., 0., -1.]))}
        results.append(result)
        return result
    monkeypatch.setattr(flexure, 'spec_flex_shift', correlate)
    original = [a.copy() for a in grid]
    record, arrays = sky.compare(*grid, ranges=[(5400, 8500), (5400, 5410)])
    assert record['status'] == 'diagnostic_only' and record['applied'] is False
    assert record['wavelength_medium'] == 'vacuum'
    assert record['ranges'][0]['status'] == 'measured'
    assert record['ranges'][1]['status'] == 'insufficient_coverage'
    assert not arrays['valid'][100:110].any()
    assert np.isnan(arrays['sky_electron'][100:110]).all()
    assert np.max(captured[0].flux) < 12.
    assert np.all(arrays['wave_vacuum'] > grid[1][:, 0])
    np.testing.assert_array_equal(arrays['correlation_0'], results[0]['corr'])
    np.testing.assert_array_equal(arrays['lags_0'], results[0]['subpix'])
    for actual, before in zip(grid, original): np.testing.assert_array_equal(actual, before)


@pytest.mark.parametrize('result', [None, ValueError('unmeasurable'), RuntimeError('failed fit')])
def test_unmeasurable_correlation_is_retained_as_failed_diagnostic(grid, template_path, monkeypatch, result):
    from pypeit.core import flexure
    def correlate(*args, **kwargs):
        if isinstance(result, Exception): raise result
        return result
    monkeypatch.setattr(flexure, 'spec_flex_shift', correlate)
    record, _ = sky.compare(*grid, ranges=[(5400, 8500)])
    assert record['ranges'][0]['status'] == 'failed'
    assert record['ranges'][0]['reason']
    assert not sky.quality_passed(record)


def test_invalid_grids_are_rejected(grid):
    data, wave, good = grid
    with pytest.raises(ValueError, match='two-dimensional'): sky.compare(data[:, 0], wave, good)
    with pytest.raises(ValueError, match='increase'): sky.compare(data, wave[::-1], good)


def accepted(shift):
    return {'ranges': [{'status': 'measured', 'coverage_fraction': 1.,
        'approximate_shift_angstrom': shift, 'quality': {'peak_correlation': .9,
        'separated_peak_margin': .2, 'pypeit_peak_disagreement_pixels': .1,
        'concave_peak': True, 'edge_peak': False}} for _ in range(4)]}


def test_validated_shift_is_remeasured_on_air_grid_without_mutating_inputs(grid, monkeypatch):
    calls = []
    def compare(data, wave, good):
        calls.append(wave.copy())
        return accepted(-2. if len(calls) == 1 else .1), {'sky': data.copy()}
    monkeypatch.setattr(sky, 'compare', compare)
    original = grid[1].copy()
    shift, record = sky.measure_validated(*grid)
    assert shift == -2. and record['validation_passed']
    assert record['held_out_6363_pass'] is False
    np.testing.assert_array_equal(calls[1], original - 2.)
    np.testing.assert_array_equal(grid[1], original)


@pytest.mark.parametrize('failure', ['initial-quality', 'corrected-quality', 'corrected-residual'])
def test_failed_validation_preserves_diagnostic_evidence(grid, monkeypatch, failure):
    before = accepted(-2.); after = accepted(.1)
    if failure == 'initial-quality': before['ranges'][0]['quality']['edge_peak'] = True
    elif failure == 'corrected-quality': after['ranges'][0]['coverage_fraction'] = .5
    else:
        after = accepted(2.)  # consistent, but not close enough to zero after correction
    answers = iter([(before, {'before': np.array([1])}), (after, {'after': np.array([2])})])
    monkeypatch.setattr(sky, 'compare', lambda *args: next(answers))
    with pytest.raises(SkyValidationError) as caught: sky.measure_validated(*grid)
    assert caught.value.diagnostics['full_sky'] is before
    if failure != 'initial-quality':
        assert caught.value.diagnostics['corrected_full_sky'] is after


def test_regional_disagreement_rejects_otherwise_strong_correlation():
    record = accepted(0.)
    record['ranges'][2]['approximate_shift_angstrom'] = 4.
    assert not sky.quality_passed(record)


@pytest.mark.parametrize('changed', [False, True])
def test_saved_comparison_binds_recipe_masks_and_input_hashes(tmp_path, monkeypatch, changed):
    import json
    from efospec import revisions
    from efospec.inventory import sha256
    from efospec.recipes import DetectorWindow
    run = tmp_path / 'run'; run.mkdir(); (run / 'run.json').write_text('{}')
    hashes = {'raw': 'a'*64, 'images': 'b'*64, 'manifest': 'c'*64}
    shape = (100, 141)
    bad = np.zeros(shape, bool); bad[:, 10] = True
    exposure = SimpleNamespace(run=run, hashes=hashes, window=DetectorWindow(shape, (4, 99)),
        frame={'sha256': hashes['raw']}, result={'object': 'synthetic'},
        context=SimpleNamespace(data=np.ones(shape), waveair=np.ones(shape)*6000,
                                processed={'bad_pixels': bad}))
    recipe = {'schema_version': 1, 'engine_version': '3.0.0',
        'coordinates': 'raw_detector_pixels_zero_based', 'input_sha256': hashes, 'source_mode': 'manual',
        'objects': [{'id': 'primary', 'label': 'Target', 'kind': 'point', 'spec': 50., 'spat': 140., 'fwhm': 3., 'radius': 6.}],
        'sky': {'mode': 'regions', 'include': [[100., 130.], [160., 230.]], 'exclude': [[175., 185.]]}}
    count = 0
    def load(*args):
        nonlocal count
        count += 1
        if changed and count == 2:
            return SimpleNamespace(hashes=dict(hashes, raw='d'*64))
        return exposure
    monkeypatch.setattr(revisions, 'FailedExposure', load)
    def compare(data, wave, good):
        assert good[:, 11].all()
        assert not good[:, [0, 10, 41, 81, 140]].any()
        return {'status': 'diagnostic_only', 'applied': False}, {'valid': good}
    monkeypatch.setattr(sky, 'compare', compare)
    output = tmp_path / 'comparison'
    if changed:
        with pytest.raises(ValueError, match='inputs changed'):
            sky.run_comparison(run, 'raw.fits', recipe, output)
        assert not (output / 'comparison.json').exists()
    else:
        record = sky.run_comparison(run, 'raw.fits', recipe, output)
        assert record['parent_sha256'] == sha256(run / 'run.json')
        assert record['raw_sha256'] == hashes['raw']
        assert record['input_sha256'] == hashes
        assert json.loads((output / 'recipe.json').read_text())['sky'] == recipe['sky']
        assert (output / 'comparison.npz').exists()
        with pytest.raises(FileExistsError):
            sky.run_comparison(run, 'raw.fits', recipe, output)
