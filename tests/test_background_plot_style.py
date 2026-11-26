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



def test_extraction_preview_keeps_raw_coordinates_and_invalid_wave_counts():
    from types import SimpleNamespace
    from efospec.background_qc import draw_extraction
    from efospec.recipes import DetectorWindow
    data=np.arange(600,dtype=float).reshape(20,30)
    exposure=SimpleNamespace(images={'data':data,'sky':data*.9,'found_traces':np.full((1,20),15.)},
        window=DetectorWindow(data.shape,(100,500)),result={'object':'ATtest'})
    recipe={'objects':[{'radius':3,'spat':515.,'spec':110.}], 'sky':{'include':[[501,508],[522,528]]}}
    result={'trace_raw':np.full(20,515.),'counts':np.arange(20.),'variance':np.ones(20),
            'valid':np.ones(20,dtype=bool),'spectrum_valid':np.zeros(20,dtype=bool)}
    fig=Figure(figsize=(18,11));draw_extraction(fig,exposure,recipe,result)
    image_ax,profile_ax,count_ax=fig.axes
    assert tuple(image_ax.images[0].get_extent())==(499.5,529.5,99.5,119.5)
    np.testing.assert_array_equal(count_ax.lines[0].get_xdata(),np.arange(100,120))
    np.testing.assert_array_equal(count_ax.lines[0].get_ydata(),result['counts'])
    assert 'Raw spectral row' in count_ax.get_xlabel()
    assert 'no flux or wavelength acceptance' in fig.profile_display['counts']
    assert image_ax.get_position().height>2*profile_ax.get_position().height
    for ax in (image_ax,profile_ax):
        assert sum(getattr(p,'_efospec_background',False) for p in ax.patches)==2
    assert len(fig.legends)==1
    assert all(np.isclose(t.get_fontsize(),23.4) for t in count_ax.get_xticklabels())
