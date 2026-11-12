"""Candidate peaks and row-subset profiles must survive QC display limits."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from efospec.recovery_qc import plot_exposure, _profile_limit_samples, _profile_limits


@pytest.mark.parametrize('sky_available', [False, True])
def test_failed_profile_shows_reviewed_c2_and_wavelength_dependent_centroids(sky_available):
    from efospec.profile_plot import draw_review_profiles
    import matplotlib.pyplot as plt
    ny, nx = 60, 101
    x = np.arange(nx)
    traces = np.array([np.full(ny, 20.), np.linspace(45., 55., ny)])
    data = 100+300*np.exp(-.5*((x[None, :]-traces[1, :, None])/3)**2)
    mask = np.broadcast_to(((x > 28)&(x < 35))|((x > 65)&(x < 72)), data.shape)
    images = dict(data=data, waveair=np.broadcast_to(np.linspace(4000, 7000, ny)[:, None], data.shape),
        found_traces=traces, sky=np.full_like(data, 100.), sky_input_mask=mask,
        sky_mask_stage='bounded_input_and_post_rejection_masks' if sky_available
                       else 'source_finding_only_no_accepted_background_fit')
    original = {k:v.copy() for k,v in images.items() if isinstance(v, np.ndarray)}
    selection = dict(candidate=2, radius_pixels=7., radius_source='review recipe',
                     aperture_label='Reviewed aperture', method='operator_visual')
    fig, record = draw_review_profiles(images, dict(object='SNtest', grism='Gr13', exptime_s=900),
        spatial_origin=100, selection=selection, candidate_notes={'C1':'unconfirmed'})
    assert record['selection']==selection
    assert record['display_only'] and not record['extraction_accepted']
    centers=[]
    for ax, profile in zip(fig.axes, record['bins']):
        # A positive observed baseline stays positive even when an unavailable
        # model has saved sampling bands but must not be drawn as zero.
        assert ax.get_ylim()[0]>0
        assert max(profile['aperture_fraction']) > .9
        assert any(t.get_text()=='C1' and t.get_position()[0]==pytest.approx(profile['median_trace_pixel']+1)
                   for t in ax.texts)
        assert all('centre:' not in t.get_text() for t in ax.texts)
        centers.append(profile['median_trace_pixel'])
        assert next(c for c in profile['candidate_centroids'] if c['label']=='C1')['spatial_pixel']==pytest.approx(centers[-1])
        assert record['display_label_map']=={'C2':'C1'}
        assert record['selection']['candidate']==2
        assert bool(np.any(profile['background_fraction']))==sky_available
        assert np.max(ax.images[1].get_array()[..., 3]) > 0
    assert centers[0] < centers[1] < centers[2]
    for key, value in original.items(): np.testing.assert_array_equal(images[key], value)
    plt.close(fig)


def test_removed_wing_cannot_reappear_and_broad_neighbour_gets_c2_label():
    from efospec.profile_plot import draw_review_profiles
    import matplotlib.pyplot as plt
    shape=(30,201)
    images=dict(data=np.ones(shape),waveair=np.broadcast_to(np.linspace(4000,7000,30)[:,None],shape),
                found_traces=np.array([np.full(30,100.),np.full(30,142.)]))
    selection=dict(candidate=1,radius_pixels=16.,radius_source='proposed FWHM width',method='operator_visual')
    fig,record=draw_review_profiles(images,dict(object='SNtest',grism='Gr13',exptime_s=900),
        selection=selection,hidden_candidates=['C2'],candidate_labels={'N1':'C2'},
        candidate_evidence={'N1':{'accepted':True}},
        supplemental_traces=[dict(label='N1',trace=np.full(30,160.))])
    for ax,b in zip(fig.axes,record['bins']):
        markers=[line.get_xdata()[0] for line in ax.lines if len(line.get_xdata())==2]
        assert markers==[100.,160.]
        labels=[t.get_text() for t in ax.texts]
        assert 'C1' in labels and 'C2' in labels and 'N1' not in labels
        assert [c['spatial_pixel'] for c in b['candidate_centroids']]==[100.,160.]
    assert record['hidden_candidates']==['C2'] and record['candidate_labels']=={'N1':'C2'}
    np.testing.assert_array_equal(images['found_traces'][1],np.full(30,142.))
    plt.close(fig)


@pytest.mark.parametrize('source', ['review', 'saved_packet', 'missing'])
def test_reviewed_profiles_do_not_promote_rejected_or_unvalidated_traces(source):
    from efospec.profile_plot import draw_review_profiles
    import matplotlib.pyplot as plt
    shape=(30,201)
    images=dict(data=np.ones(shape),waveair=np.broadcast_to(np.linspace(4000,7000,30)[:,None],shape),
        found_traces=np.array([np.full(30,p) for p in (60.,103.,145.)]),
        found_names=np.array(['left','target','right']))
    evidence={'C1':{'accepted':False},'C2':{'accepted':True},'C3':{'accepted':False}}
    kwargs={}
    if source=='review': kwargs['candidate_evidence']=evidence
    if source=='saved_packet':
        images['candidate_evidence_json']=np.array(json.dumps({name:evidence[f'C{i+1}']
            for i,name in enumerate(images['found_names'])}))
    selection=dict(candidate=2,radius_pixels=7.,radius_source='review recipe',method='operator_visual')
    fig,record=draw_review_profiles(images,dict(object='SNtest',grism='Gr13',exptime_s=900),
        selection=selection,candidate_notes={'C1':'Unconfirmed'},**kwargs)
    for ax,b in zip(fig.axes,record['bins']):
        assert [c['label'] for c in b['candidate_centroids']]==['C1']
        assert [c['source_label'] for c in b['candidate_centroids']]==['C2']
        assert [line.get_xdata()[0] for line in ax.lines if len(line.get_xdata())==2]==[103.]
        assert all(t.get_text() not in ('C1?','C3?','C2','C3') for t in ax.texts)
    assert set(record['validation_hidden_candidates'])=={'C1','C3'}
    plt.close(fig)


@pytest.mark.parametrize('sky_available,bounded', [(True, False), (False, False), (True, True)])
def test_all_three_candidates_and_median_curves_are_visible(tmp_path, monkeypatch, sky_available, bounded):
    ny, nx = 40, 141
    x = np.arange(nx)
    signal = sum(amp*np.exp(-.5*((x-center)/1.2)**2)
                 for center, amp in [(15, 80), (70, 300), (125, 1200)])
    data = np.broadcast_to(signal+100, (ny, nx)).copy()
    data[ny//4:ny//2] += 2000  # The old mean/percentile limits clipped this curve.
    data[:,5] = -10000  # Draw this dip but do not let it set the y-limits.
    raw = tmp_path/'raw.fits'
    fits.writeto(raw, data)
    names = ['third', 'first', 'second']
    traces = np.broadcast_to(np.array([125., 15., 70.])[:, None], (3, ny)).copy()
    exposure = SimpleNamespace(frame={'path': str(raw)}, result={'object': 'SNtest'},
        window=SimpleNamespace(origin=(10, 100)),
        candidates=[{'name': n} for n in ['first', 'second', 'third']],
        images={'data': data, 'sky': np.full_like(data, 100) if sky_available else np.zeros_like(data),
                'found_names': names, 'found_traces': traces,
                'waveair':np.broadcast_to(np.linspace(4000,7000,ny)[:,None],data.shape),
                'sky_input_mask':np.broadcast_to((x>5)&(x<135),data.shape),
                'sky_mask_stage': np.array('bounded_input_and_post_rejection_masks' if sky_available
                                          else 'source_finding_only_no_background_fit')})
    figures = {}
    monkeypatch.setattr('efospec.figure_style.save_qc', lambda fig, output, kind, name, **kw: figures.update({kind: fig}))
    monkeypatch.setattr('efospec.profile_plot.save_review_profile',lambda fig,*a:figures.update(profiles=fig))
    if bounded:
        monkeypatch.setattr('efospec.profile_background.load_profile_background', lambda *args: {
            'residual': data-exposure.images['sky'], 'valid_rows': np.ones(ny, dtype=bool),
            'x_limits': (150., 230.), 'provenance': None})
    plot_exposure(exposure, tmp_path)
    assert set(figures) == {'science', 'traces', 'profiles'}
    assert len(figures['traces'].axes) == 2
    for kind in ('science','traces'):
        assert all(ax.images[0].get_cmap().name=='gray_r' for ax in figures[kind].axes if ax.images)
    panels=figures['profiles'].axes
    assert len(panels)==3
    saved=json.loads((tmp_path/'profile-display.json').read_text())
    for ax,record in zip(panels,saved['bins']):
        np.testing.assert_allclose(ax.lines[0].get_ydata(),
            np.asarray(record['summed_data_electrons'],dtype=float)/1000.)
        assert ax.lines[0].get_color()=='0.3'
        assert 'After subtraction' not in ax.get_title()
        markers=[line.get_xdata()[0] for line in ax.lines if len(line.get_xdata())==2]
        assert markers==[115.,170.,225.]
        assert ax.get_ylim()[1]>np.nanmax(ax.lines[0].get_ydata())
    assert saved['model_available']==sky_available
    assert saved['sky_subtracted'] is False
    if not sky_available:
        assert 'no accepted background' in panels[0].get_title()
        assert all(line.get_color()!='xkcd:dark blue' for line in panels[0].lines)
    assert all(t.get_fontsize()==pytest.approx(18) for t in panels[0].get_legend().get_texts())
    assert saved['profile_statistic'].startswith('sum ')


def test_limit_samples_exclude_narrow_outliers_and_protect_candidates():
    x = np.arange(100)
    values = 100+np.sin(x)
    values[15] -= 80
    values[30:32] -= 80
    values[45] += 800  # A narrow source peak must survive.
    values[60:70] -= 80  # A broad depression must survive.
    values[85] -= 80  # Even a narrow dip near a candidate stays visible.
    original = values.copy()
    protected = (np.abs(x-85) <= 3)|(np.abs(x-45)<=3)
    shown, masked = _profile_limit_samples(values, protected)
    assert np.flatnonzero(masked).tolist() == [15,30,31]
    assert np.isnan(shown[masked]).all()
    np.testing.assert_array_equal(shown[~masked], original[~masked])
    np.testing.assert_array_equal(values, original)


def test_explicit_positive_spike_limit_mask_preserves_neighbour_and_science_data():
    x=np.arange(400,551)
    values=10+100*np.exp(-.5*((x-450)/3)**2)+180*np.exp(-.5*((x-515)/6)**2)
    values[x==547]=2000
    original=values.copy()
    protected=(abs(x-450)<=7)|(abs(x-515)<=10)
    retained,masked=_profile_limit_samples(values,protected,spatial_pixel=x,exclude_ranges=[[546,549]])
    assert x[masked].tolist()==[546,547,548]
    low,high=_profile_limits([retained],background_subtracted=True)
    assert values[x==450][0]<high and values[x==515][0]<high<values[x==547][0]
    np.testing.assert_array_equal(values,original)
    with pytest.raises(ValueError,match='protected source'):
        _profile_limit_samples(values,protected,spatial_pixel=x,exclude_ranges=[[510,520]])


@pytest.mark.parametrize('values,expected', [([100,200],(90,220)),
    ([-200,-100],(-220,-90)), ([-100,200],(-110,220)), ([0,0],(-.1,.1))])
def test_profile_limits_pad_outward_without_forcing_zero(values, expected):
    assert _profile_limits([np.asarray(values)]) == pytest.approx(expected)


def test_slit_edge_columns_stay_plotted_but_do_not_set_the_profile_scale():
    """Off-slit boundary spikes overwhelm the sources by an order of magnitude."""
    x = np.arange(120)
    values = 10.+np.sin(x/7.)
    values[55] += 250.          # the source peak must frame the viewport
    values[:2] += 4000.         # slit boundary, no fitted background
    values[-2:] += 4000.
    protected = np.abs(x-55) <= 3
    original = values.copy()
    shown, masked = _profile_limit_samples(values, protected, edge_margin=3)
    assert np.flatnonzero(masked).tolist() == [0, 1, 2, 117, 118, 119]
    np.testing.assert_array_equal(values, original)   # samples themselves untouched
    low, high = _profile_limits([shown], background_subtracted=True)
    assert high < 400. and low <= 0.
    # Without the margin the boundary runs set the scale and hide the source.
    plain, _ = _profile_limit_samples(values, protected)
    assert _profile_limits([plain], background_subtracted=True)[1] > 4000.


def test_edge_margin_never_drops_a_protected_column_and_is_validated():
    x = np.arange(40)
    values = np.ones(40)
    protected = x <= 2                      # a candidate sitting on the boundary
    shown, masked = _profile_limit_samples(values, protected, edge_margin=3)
    assert not masked[:3].any() and masked[-3:].all()
    for bad in (-1, 20, 2.5):
        with pytest.raises(ValueError, match='edge margin'):
            _profile_limit_samples(values, protected, edge_margin=bad)
