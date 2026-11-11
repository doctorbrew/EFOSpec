"""Candidate peaks and row-subset profiles must survive QC display limits."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from efospec.recovery_qc import plot_exposure, _profile_limit_samples, _profile_limits


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
                'sky_mask_stage': np.array('bounded_input_and_post_rejection_masks' if sky_available
                                          else 'source_finding_only_no_background_fit')})
    figures = {}
    monkeypatch.setattr('efospec.figure_style.save_qc', lambda fig, output, kind, name, **kw: figures.update({kind: fig}))
    if bounded:
        monkeypatch.setattr('efospec.profile_background.load_profile_background', lambda *args: {
            'residual': data-exposure.images['sky'], 'valid_rows': np.ones(ny, dtype=bool),
            'x_limits': (150., 230.), 'provenance': None})
    plot_exposure(exposure, tmp_path)
    assert set(figures) == {'science', 'traces', 'profiles'}
    assert len(figures['traces'].axes) == 2
    for kind in ('science','traces'):
        assert all(ax.images[0].get_cmap().name=='gray_r' for ax in figures[kind].axes if ax.images)
    profile = figures['profiles'].axes[0]
    low, high = profile.get_ylim()
    residual = data-exposure.images['sky']
    statistic = np.sum if sky_available else np.median
    expected = [statistic(residual,axis=0),statistic(residual[ny//4:ny//2],axis=0),
                statistic(residual[ny//2:3*ny//4],axis=0)]
    for line, values in zip(profile.lines[3:], expected):
        if bounded:
            values[(x+100 < 150) | (x+100 > 230)] = np.nan
        np.testing.assert_array_equal(line.get_ydata(), values/1000.)
        assert line.get_linewidth() == 2.
        if not bounded:
            assert line.get_ydata()[5] < low
        assert np.nanmax(line.get_ydata()) < high
    assert [line.get_xdata()[0] for line in profile.lines[:3]] == [115., 170., 225.]
    assert [line.get_color() for line in profile.lines[:3]] == ['xkcd:red']*3
    assert [line.get_linestyle() for line in profile.lines[:3]] == ['-', '--', '-.']
    assert all(line.get_linewidth() == 4.2 for line in profile.lines[:3])
    assert profile.get_legend_handles_labels()[1] == ['Full range: y=10--49','Q2: y=20--29','Q3: y=30--39']
    assert profile.get_legend()._ncols == 3
    for ax in [figures['science'].axes[1], figures['traces'].axes[1], profile]:
        assert [text.get_text() for text in ax.texts] == ['C1','C2','C3']
        for text in ax.texts:
            assert ax.get_xlim()[0] < text.get_position()[0] < ax.get_xlim()[1]
            assert text.get_rotation() == 90
            assert text.get_position()[1] == .03
            assert text.get_verticalalignment() == 'bottom'
            assert text.get_fontsize() == pytest.approx(21.6)
            assert text.get_bbox_patch().get_alpha() == .7
    assert figures['traces'].axes[1].get_legend_handles_labels()[1] == []
    assert figures['science'].axes[1].get_legend_handles_labels()[1] == []
    assert figures['profiles'].get_figheight() == 8.5
    for line in figures['traces'].axes[1].lines:
        ax = line.axes
        assert ax.get_xlim()[0] < min(line.get_xdata()) < ax.get_xlim()[1]
        assert ax.get_ylim()[0] < min(line.get_ydata()) <= max(line.get_ydata()) < ax.get_ylim()[1]
    assert ('Summed Bkg-Subtracted Signal' in profile.get_ylabel()) == sky_available
    assert profile.get_xlabel() == 'Spatial Pixel'
    assert profile.xaxis.label.get_fontsize() == pytest.approx(28.6)
    assert profile.yaxis.label.get_fontsize() == pytest.approx(28.6)
    assert all(text.get_fontsize() == pytest.approx(23.4) for text in profile.get_legend().get_texts())
    assert figures['profiles']._suptitle.get_text() == 'SNtest'
    # The figure keeps a short title; the summation rule and row ranges stay in
    # profile-display.json and the report caption.
    assert profile.get_title() == ('Spatial profile' if sky_available
                                   else 'Spatial profile (sky included)')
    saved = json.loads((tmp_path/'profile-display.json').read_text())
    assert saved['profile_statistic'].startswith('sum ' if sky_available else 'median ')
    assert saved['slit_edge_margin_columns'] == 3
    assert r'10^3\,e^{-}' in profile.get_ylabel()
    assert ('unavailable' in figures['traces']._suptitle.get_text()) != sky_available


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
