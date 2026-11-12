import numpy as np
import pytest
from efospec.trace_geometry import trace_evidence, measured_aperture, background_limits


def fixture(amplitude=70., sigma=2., seed=32):
    rng=np.random.default_rng(seed)
    y,x=np.indices((240,141));trace=70+.7*((np.arange(240)-120)/120)**2
    data=100+.15*x+amplitude*np.exp(-.5*((x-trace[:,None])/sigma)**2)+rng.normal(0,5,x.shape)
    return data,np.full(data.shape,1/25),trace


def test_local_contrast_accepts_curved_source_but_rejects_sky_gradient():
    data,ivar,trace=fixture()
    assert trace_evidence(data,ivar,trace,4.71)['accepted']
    data,ivar,trace=fixture(amplitude=0)
    assert not trace_evidence(data,ivar,trace,4.71)['accepted']


def test_single_spectral_spike_and_support_boundary_need_review():
    data,ivar,trace=fixture(amplitude=0)
    data[40,68:73]+=10000
    assert not trace_evidence(data,ivar,trace,4.71)['accepted']
    data,ivar,trace=fixture()
    support=np.indices(data.shape)[1]>69
    assert not trace_evidence(data,ivar,trace,4.71,support=support)['accepted']


def test_curved_monotonic_wing_needs_a_turnover_not_just_gaussian_contrast():
    rng=np.random.default_rng(102)
    y,x=np.indices((240,141));trace=np.full(240,70.)
    # Concave curvature projects onto a positive Gaussian even though the
    # entire local profile is increasing: there is no source centred here.
    data=1000+4*x-.05*(x-70)**2+rng.normal(0,2,x.shape)
    check=trace_evidence(data,np.full(data.shape,.25),trace,8.)
    assert not check['accepted']
    assert all(b['snr']>3 for b in check['bins'])
    assert all(not b['turnover'] for b in check['bins'])


def test_broad_peak_is_kept_and_an_unsupported_flank_is_not_a_peak():
    data,ivar,trace=fixture(amplitude=100,sigma=8.)
    check=trace_evidence(data,ivar,trace,18.84)
    assert check['accepted'] and all(b['turnover'] for b in check['bins'])
    support=np.indices(data.shape)[1]<75
    assert not trace_evidence(data,ivar,trace,18.84,support=support)['accepted']


def test_aperture_grows_with_seeing_and_encloses_core():
    radii=[]
    for sigma in (1.5,3.):
        data,ivar,trace=fixture(sigma=sigma)
        radius,info=measured_aperture(data,ivar,trace,sigma*2.35482)
        assert radius>=3*sigma
        assert not info['total_flux_guaranteed']
        radii.append(radius)
    assert radii[1]>radii[0]


def test_neighbour_prevents_unsupported_total_flux_claim():
    data,ivar,trace=fixture()
    with pytest.raises(ValueError,match='room'):
        measured_aperture(data,ivar,trace,4.71,neighbours=[(trace+8,4.,5.)])


def test_background_view_ignores_bad_slit_edge():
    model=np.full(100,100.);profile=model+np.random.default_rng(2).normal(0,2,100)
    profile[50]+=30;profile[0]=-1e8
    (low,high),info=background_limits(profile,model)
    assert 90<low<100<high<140


def test_background_curve_is_visible_when_it_varies_below_its_median():
    model=np.linspace(1080.,1180.,100)
    profile=model+np.random.default_rng(3).normal(0,2,100)
    profile[50]+=300
    (low,high),info=background_limits(profile,model)
    assert low < model[3:-3].min() < 1100
    assert high > max(model[3:-3].max(),profile[3:-3].max())
