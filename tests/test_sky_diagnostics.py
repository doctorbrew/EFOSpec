import json
from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from efospec.inventory import sha256
from efospec.native_sky import SkyValidationError
from efospec.sky_comparison import measure_validated,quality_passed
from efospec.sky_diagnostics import summarize,save_failure_packet,diagnose,fit_peak


def record():
    return dict(ranges=[dict(status='measured',coverage_fraction=1.,approximate_shift_angstrom=-4.,
        range_vacuum_angstrom=[5200.,9000.],quality=dict(peak_correlation=.9,separated_peak_margin=.3,
        pypeit_peak_disagreement_pixels=.1,concave_peak=True,edge_peak=False)) for _ in range(4)])


def test_localized_warning_does_not_accept_failed_wavelengths():
    r=record();r['ranges'][3]['approximate_shift_angstrom']=0.
    assert summarize(r)['localized_warning_candidate']
    assert not summarize(r)['accepted'] and not quality_passed(r)
    r['ranges'][0]['quality']['peak_correlation']=.1
    assert not summarize(r)['localized_warning_candidate']
    r=record();r['ranges'][2]['approximate_shift_angstrom']=0;r['ranges'][3]['approximate_shift_angstrom']=1
    assert not summarize(r)['localized_warning_candidate']


def test_corrected_residual_and_missing_coverage_are_named():
    r=record()
    for x in r['ranges']:x['approximate_shift_angstrom']=0.
    r['ranges'][3]['approximate_shift_angstrom']=2.
    assert 'corrected_residual' in summarize(r,corrected=True)['ranges'][3]['failed_checks']
    r['ranges'][3]['coverage_fraction']=.1
    assert 'coverage' in summarize(r)['ranges'][3]['failed_checks']


def test_failure_preserves_input_and_retains_arrays(monkeypatch,tmp_path):
    import efospec.sky_comparison as module
    r=record();r['ranges'][3]['approximate_shift_angstrom']=1.
    retained={'observed_0':np.arange(80.)}
    monkeypatch.setattr(module,'compare',lambda *args:(r,retained))
    data=np.ones((80,12));wave=data*6000.;good=data.astype(bool)
    original=data.copy()
    with pytest.raises(SkyValidationError) as raised:measure_validated(data,wave,good)
    assert np.array_equal(data,original)
    raw=tmp_path/'raw.fits';raw.write_bytes(b'raw')
    pointer=save_failure_packet(tmp_path/'packet',raised.value,data,wave,good,
        raw=str(raw),raw_sha256=sha256(raw),target='SNtest')
    manifest=Path(pointer['path']);saved=json.loads(manifest.read_text())
    assert sha256(manifest)==pointer['sha256'] and saved['assessment']['localized_warning_candidate']
    with np.load(manifest.parent/'arrays.npz') as a:
        assert np.array_equal(a['input_data'],original)
        assert np.array_equal(a['before__observed_0'],retained['observed_0'])
    (manifest.parent/'arrays.npz').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='arrays changed'):diagnose(manifest,tmp_path/'qc')
    assert not (tmp_path/'qc').exists()


def test_corrected_failure_keeps_both_stages(monkeypatch):
    import efospec.sky_comparison as module
    before=record();after=deepcopy(before)
    for x in after['ranges']:x['approximate_shift_angstrom']=2.
    calls=iter([(before,{'tag':np.array([1])}),(after,{'tag':np.array([2])})])
    monkeypatch.setattr(module,'compare',lambda *a:next(calls))
    with pytest.raises(SkyValidationError) as raised:measure_validated(np.ones((80,12)),np.ones((80,12)),np.ones((80,12),bool))
    assert set(raised.value.sky_diagnostic_arrays)=={'before','after'}


def test_peak_fits_recover_known_lag_and_reject_flat_correlation():
    x=np.arange(100)-50;c=10-(x+.75)**2
    for points in (3,5,7):assert fit_peak(c,points)==pytest.approx(-.75)
    with pytest.raises(ValueError):fit_peak(np.zeros(100))


def test_real_red_region_reproduces_clipping_sensitivity_without_mutating_inputs():
    import pypeit
    from efospec.sky_diagnostics import clipping_trials
    if pypeit.__version__!='3.0.0':pytest.skip('PypeIt 3.0.0 reconstruction contract')
    path=Path(__file__).parent/'data/abgb-red-sky-correlation.npz'
    provenance=json.loads(path.with_suffix('.json').read_text())
    assert sha256(path)==provenance['fixture_sha256']
    with np.load(path) as f:values={k:f[k] for k in f.files}
    before={k:v.copy() for k,v in values.items()}
    record,_=clipping_trials(values,3)
    assert record['status']=='baseline_reproduced'
    assert record['production_shift_pixels']==pytest.approx(-.061163012875269374,abs=1e-6)
    assert record['trials']['without_initial_observed_clip']['shift_pixels']==pytest.approx(-.61312535295,abs=1e-6)
    assert all(np.array_equal(values[k],v) for k,v in before.items())
    values['correlation_3']*=2
    record,arrays=clipping_trials(values,3)
    assert record['status']=='baseline_reconstruction_mismatch' and not arrays


def test_unrecognized_pypeit_version_suppresses_reconstruction(monkeypatch):
    import pypeit
    from efospec.sky_diagnostics import clipping_trials
    monkeypatch.setattr(pypeit,'__version__','future-version')
    assert clipping_trials({},0)==({'status':'unsupported_pypeit_version'},{})


def test_cli_forwards_diagnostic_trial_without_accepting_products(monkeypatch,capsys):
    from efospec.__main__ import main
    import efospec.sky_diagnostics as module
    calls=[]
    def fake(packet,output,*,trial_correction=False):
        calls.append((packet,output,trial_correction));return dict(status='complete',errors=[])
    monkeypatch.setattr(module,'diagnose',fake)
    assert main(['sky-diagnose','packet.json','--output','new-qc','--trial-correction'])==0
    assert calls==[('packet.json','new-qc',True)]
    assert json.loads(capsys.readouterr().out)['status']=='complete'
