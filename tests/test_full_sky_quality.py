from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from efospec.sky_comparison import correlation_quality, quality_passed
from efospec.native_sky import wavelength_accepted


def correlation(a,b,shift=0):
    return dict(sky_spec=SimpleNamespace(flux=a),arx_spec=SimpleNamespace(flux=b),
                shift=shift,polyfit=SimpleNamespace(fitc=[0,0,-1]))


def test_quality_distinguishes_shifted_features_from_noise_and_continuum():
    x=np.arange(600.);b=sum(np.exp(-.5*((x-c)/3)**2) for c in [60,130,245,365,480,530])
    a=np.interp(x-1,x,b)+2+.001*x
    q=correlation_quality(correlation(a,b,-1))
    assert q['peak_correlation']>.9 and abs(q['peak_lag_pixels']+1)<.3
    assert q['separated_peak_margin']>.05
    rng=np.random.default_rng(342)
    assert correlation_quality(correlation(rng.normal(size=600),b))['peak_correlation']<.5
    assert correlation_quality(correlation(np.ones(600),b))['peak_correlation']==0


def record():
    return dict(ranges=[dict(status='measured',coverage_fraction=.99,approximate_shift_angstrom=-5.,
        quality=dict(peak_correlation=.8,separated_peak_margin=.2,pypeit_peak_disagreement_pixels=.2,
                     concave_peak=True,edge_peak=False)) for _ in range(4)])


@pytest.mark.parametrize('defect',['weak','alias','edge','missing','distortion','nan'])
def test_acceptance_rejects_unreliable_correlations(defect):
    r=record();assert quality_passed(r)
    item=r['ranges'][-1]
    if defect=='weak':item['quality']['peak_correlation']=.2
    if defect=='alias':item['quality']['separated_peak_margin']=.01
    if defect=='edge':item['quality']['edge_peak']=True
    if defect=='missing':item['coverage_fraction']=.5
    if defect=='distortion':item['approximate_shift_angstrom']=1
    if defect=='nan':item['quality']['peak_correlation']=np.nan
    assert not quality_passed(r)


def test_wavelength_acceptance_rechecks_evidence_and_corrected_residuals():
    before=record();after=deepcopy(before)
    for item in after['ranges']:item['approximate_shift_angstrom']=.1
    r=dict(validation_passed=True,validation_policy='full-spectrum',quality_policy='full-sky-v1',shift_angstrom=-5.,full_sky=before,corrected_full_sky=after)
    assert wavelength_accepted(r)
    after['ranges'][-1]['approximate_shift_angstrom']=2
    assert not wavelength_accepted(r)
