import numpy as np
from matplotlib.figure import Figure
from efospec.background_qc import profile_view_limits
from efospec.profile_limits import _profile_limit_samples,_profile_limits


def test_gui_profile_limits_match_report_and_leave_spikes_in_the_data():
    x=np.arange(101);y=10+np.sin(x)*.1+40*np.exp(-.5*((x-50)/3)**2)
    y[20]=3000.;y[80]=-3000.
    protected=abs(x-50)<8
    original=y.copy();fig=Figure();ax=fig.subplots();line=ax.plot(x,y)[0]
    info=profile_view_limits(ax,x,y,protected)
    expected,_=_profile_limit_samples(y,protected,spatial_pixel=x,edge_margin=3)
    np.testing.assert_allclose(ax.get_ylim(),_profile_limits([expected],background_subtracted=True))
    assert 20 in info['excluded_spatial_pixels'] and 80 in info['excluded_spatial_pixels']
    np.testing.assert_array_equal(line.get_ydata(),original)
    np.testing.assert_array_equal(y,original)
    assert ax.get_ylim()[1]<100
