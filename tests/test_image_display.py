"""Display contrast and zoom geometry must not alter scientific samples."""
import numpy as np
import pytest
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from astropy.io import fits
from types import SimpleNamespace

from efospec.image_display import image_normalization, mark_zoom_region
from efospec.recovery_qc import acquisition_images


def test_clipped_asinh_preserves_pixels_and_centres_residuals_on_zero():
    image = np.random.default_rng(42).normal(0, 3, (100, 120))
    image[25, 25] = 1e8
    image[26, 26] = np.nan
    before = image.copy()
    norm, metadata = image_normalization(image, residual=True)
    assert metadata['retained_samples'] < metadata['input_samples']
    assert metadata['robust_sigma'] == pytest.approx(3., rel=.08)
    assert norm(0) == pytest.approx(.5)
    assert norm(-3)+norm(3) == pytest.approx(1.)
    values = np.array([-10., -1., 0., 1., 10.])
    np.testing.assert_allclose(norm.inverse(norm(values)), values, atol=1e-12)
    np.testing.assert_array_equal(image, before)


def test_raw_normalization_and_missing_or_constant_images():
    data = np.random.default_rng(17).normal(200., 4., (30, 40))
    norm, metadata = image_normalization(data)
    assert norm(metadata['clipped_median']) == pytest.approx(.5)
    norm, metadata = image_normalization(np.full((3, 3), 200.))
    assert metadata['degenerate_scale_fallback']
    assert np.isfinite(norm(200.))
    with pytest.raises(ValueError, match='no finite'):
        image_normalization(np.full((3, 3), np.nan))


def test_zoom_outline_matches_displayed_pixel_edges():
    fig, (full, zoom) = plt.subplots(1, 2)
    zoom.imshow(np.zeros((12, 20)), extent=(40.5, 60.5, 70.5, 82.5))
    assert mark_zoom_region(full, zoom) == [40.5, 60.5, 70.5, 82.5]
    rectangle, = full.patches
    assert rectangle.get_xy() == (40.5, 70.5)
    assert rectangle.get_width() == 20
    assert rectangle.get_height() == 12
    plt.close(fig)


def test_acquisition_has_exact_zoom_box_and_shared_clipped_stretch(tmp_path, monkeypatch):
    raw = tmp_path/'raw.fits'
    header = fits.Header({'ESO OBS ID':42, 'ESO TPL ID':'EFOSC_img_acq_MoveToSlit'})
    fits.writeto(raw, np.random.default_rng(6).normal(100., 2., (500, 600)), header)
    figures = []
    monkeypatch.setattr('efospec.figure_style.save_qc', lambda fig,*a,**kw: figures.append(fig))
    exposure = SimpleNamespace(frame={'path':str(raw)}, result={'object':'SNtest'})
    record, = acquisition_images(exposure, tmp_path)
    full, zoom = figures[0].axes
    assert full.images[0].get_cmap().name == zoom.images[0].get_cmap().name == 'RdBu'
    assert full.images[0].norm is zoom.images[0].norm
    assert record['slit_orientation']['kind'] == 'orientation_only'
    assert record['slit_overlay_on_zoom_only'] is True
    # No catalogue or registered target: show the full field without inventing
    # a detector-centre target or silently excluding candidate positions.
    assert record['zoom_raw_bounds_xy'] == [-.5,599.5,-.5,499.5]
    assert full.patches[0].get_width() == 600
    assert full.patches[0].get_height() == 500


def test_bright_percentile_extends_only_the_upper_limit_for_a_saturating_trace():
    """A sky-subtracted trace must keep structure instead of saturating to black."""
    rng = np.random.default_rng(11)
    image = rng.normal(0., 5., (200, 120))
    # A trace hundreds of background sigma above zero, on ~8 per cent of columns.
    image[:, 56:64] += 4000.
    before = image.copy()
    plain, plain_meta = image_normalization(image, residual=True, samples=image[:, :40])
    wide, wide_meta = image_normalization(image, residual=True, samples=image[:, :40],
                                          bright_percentile=99.5)
    assert plain_meta['vmax'] == pytest.approx(5*plain_meta['robust_sigma'], rel=1e-6)
    assert wide_meta['vmax'] > 20*plain_meta['vmax']
    # The noise scale and the zero point are untouched: only the headroom grew.
    assert wide_meta['linear_width'] == pytest.approx(plain_meta['linear_width'])
    assert wide_meta['vmin'] == pytest.approx(plain_meta['vmin'])
    assert wide_meta['bright_percentile'] == 99.5
    assert 'percentile' in wide_meta['upper_limit_rule']
    # The default saturates the trace; the extended range separates it from noise.
    assert plain(4000.) == pytest.approx(1.) and plain(400.) == pytest.approx(1.)
    assert wide(400.) < wide(4000.) <= 1.
    # Background noise still occupies a usable part of the ramp rather than
    # collapsing to a single tone once the headroom grows.
    assert .05 < wide(5.) - wide(0.) < .4
    np.testing.assert_array_equal(image, before)
    for bad in (50., 0., 101., np.nan):
        with pytest.raises(ValueError, match='bright percentile'):
            image_normalization(image, residual=True, bright_percentile=bad)


def test_documented_slit_direction_is_confined_to_separate_acquisition_zoom(tmp_path, monkeypatch):
    raw=tmp_path/'acquisition.fits'
    # Sky position angle must not rotate the slit on unrotated detector pixels.
    header=fits.Header({'ESO OBS ID':42,'ESO TPL ID':'EFOSC_img_acq_MoveToSlit',
                        'ESO ADA POSANG':67.})
    fits.writeto(raw,np.random.default_rng(7).normal(100,2,(500,600)),header)
    figures=[]
    monkeypatch.setattr('efospec.figure_style.save_qc',lambda fig,*a,**kw:figures.append(fig))
    record, = acquisition_images(SimpleNamespace(frame={'path':str(raw)},result={'object':'SNtest'}),tmp_path)
    full,zoom=figures[0].axes
    assert not full.artists and len(zoom.artists)==1
    assert not full.lines and not zoom.lines
    assert full.get_subplotspec().colspan.start == 0
    assert zoom.get_subplotspec().colspan.start == 1
    assert record['slit_orientation']['detector_angle_deg']==0.
    assert zoom.get_xlim()==(-.5,599.5)
    assert zoom.get_ylim()==(-.5,499.5)
