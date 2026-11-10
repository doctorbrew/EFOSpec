"""Display-only spike detection must preserve apertures and broad neighbours."""
import numpy as np
import pytest
from efospec.profile_limits import _profile_limit_samples,_profile_limits


@pytest.mark.parametrize('tail',[0.,80.,25.])
def test_automatic_edge_spike_and_wings_do_not_set_profile_scale(tail):
    x=np.arange(200);y=10+.03*x+.4*np.sin(x)
    y+=100*np.exp(-.5*((x-100)/4)**2)+180*np.exp(-.5*((x-155)/6)**2)
    y[-3]+=600;y[-4]+=tail;y[-1]=np.nan
    original=y.copy();protected=abs(x-100)<=8
    shown,masked=_profile_limit_samples(y,protected)
    assert masked[-3]
    if tail:assert masked[-4]
    assert not masked[protected].any()
    assert not masked[abs(x-155)<=8].any()
    assert 190<_profile_limits([shown],background_subtracted=True)[1]<300
    np.testing.assert_array_equal(y,original)


@pytest.mark.parametrize('width',[1.3,2.,4.,8.])
def test_even_very_bright_resolved_sources_are_not_masked(width):
    x=np.arange(200);y=10+.01*np.sin(x)+100000*np.exp(-.5*((x-120)/width)**2)
    _,masked=_profile_limit_samples(y,np.zeros(200,bool))
    assert not masked[120]


def test_unresolved_peak_is_protected_when_in_selected_aperture():
    y=10+np.sin(np.arange(80));y[40]+=10000
    protect=abs(np.arange(80)-40)<=7
    _,masked=_profile_limit_samples(y,protect)
    assert not masked[40]


def test_truncated_edge_and_missing_neighbour_do_not_establish_narrow_width():
    y=10+np.sin(np.arange(80));y[-1]+=10000;y[30]=1000;y[31]=np.nan
    _,masked=_profile_limit_samples(y,np.zeros(80,bool))
    assert not masked[-1] and not masked[30]
