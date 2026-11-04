"""Candidate peaks and row-subset profiles must survive QC display limits."""
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from efospec.recovery_qc import plot_exposure, _profile_limit_samples, _profile_limits


@pytest.mark.parametrize('sky_available', [True, False])
def test_all_three_candidates_and_median_curves_are_visible(tmp_path, monkeypatch, sky_available):
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
    plot_exposure(exposure, tmp_path)
    assert set(figures) == {'science', 'traces', 'profiles'}
    assert len(figures['traces'].axes) == 2
    profile = figures['profiles'].axes[0]
    low, high = profile.get_ylim()
    residual = data-exposure.images['sky']
    statistic = np.sum if sky_available else np.median
    expected = [statistic(residual,axis=0),statistic(residual[ny//4:ny//2],axis=0),
                statistic(residual[ny//2:3*ny//4],axis=0)]
    for line, values in zip(profile.lines[3:], expected):
        np.testing.assert_array_equal(line.get_ydata(), values/1000.)
        assert line.get_linewidth() == 2.
        assert line.get_ydata()[5] < low
        assert np.max(line.get_ydata()) < high
    assert [line.get_xdata()[0] for line in profile.lines[:3]] == [115., 170., 225.]
    assert [line.get_color() for line in profile.lines[:3]] == ['xkcd:green','xkcd:dodger blue','xkcd:red']
    assert profile.get_legend_handles_labels()[1] == ['All rows: y=10--49','Q2: y=20--29','Q3: y=30--39']
    assert profile.get_legend()._ncols == 3
    for ax in [figures['science'].axes[1], figures['traces'].axes[1], profile]:
        assert [text.get_text() for text in ax.texts] == ['C1','C2','C3']
        for text in ax.texts:
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
    assert 'dispersion axis - y' in profile.get_title()
    assert r'10^3\,e^{-}' in profile.get_ylabel()
    assert ('unavailable' in figures['traces']._suptitle.get_text()) != sky_available


def test_limit_samples_exclude_only_narrow_negative_outliers_and_protect_candidates():
    x = np.arange(100)
    values = 100+np.sin(x)
    values[15] -= 80
    values[30:32] -= 80
    values[45] += 800  # A narrow source peak must survive.
    values[60:70] -= 80  # A broad depression must survive.
    values[85] -= 80  # Even a narrow dip near a candidate stays visible.
    original = values.copy()
    protected = np.abs(x-85) <= 3
    shown, masked = _profile_limit_samples(values, protected)
    assert np.flatnonzero(masked).tolist() == [15,30,31]
    assert np.isnan(shown[masked]).all()
    np.testing.assert_array_equal(shown[~masked], original[~masked])
    np.testing.assert_array_equal(values, original)


@pytest.mark.parametrize('values,expected', [([100,200],(90,220)),
    ([-200,-100],(-220,-90)), ([-100,200],(-110,220)), ([0,0],(-.1,.1))])
def test_profile_limits_pad_outward_without_forcing_zero(values, expected):
    assert _profile_limits([np.asarray(values)]) == pytest.approx(expected)
