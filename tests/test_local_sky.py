"""Two-sided spatial sampling and the actual PypeIt background kernel."""
import numpy as np
import pytest

from efospec.local_sky import BackgroundSupportError, nearby_mask, fit_background, side_counts


def test_bands_follow_curved_trace_avoid_neighbour_and_keep_fixed_width():
    trace = 95+3*np.sin(np.arange(100)/25.)
    neighbour = trace+22
    mask, bounds = nearby_mask((100, 240), trace, radius=6., fwhm=4., width_pixels=40,
                              neighbours=[(neighbour, 4., 6.)])
    assert np.all(side_counts(mask, trace, 6.) == 40)
    assert np.all(bounds[:, :, 1]-bounds[:, :, 0] == 40)
    assert not mask[:, :3].any() and not mask[:, -3:].any()
    x = np.arange(240)
    assert not np.any(mask & (abs(x-neighbour[:, None]) <= 6.5))
    assert np.all(bounds[:, 1, 0] > neighbour+6.5)
    assert np.ptp(bounds[:, 0, 0]) > 2


def test_crowding_or_window_edge_never_falls_back_to_one_side_or_whole_slit():
    trace = np.full(40, 70.)
    with pytest.raises(BackgroundSupportError, match='both sides'):
        nearby_mask((40, 141), trace, radius=7., fwhm=5., width_pixels=40,
                    neighbours=[(trace+23., 6., 7.), (trace+50., 5., 7.)])


def test_authorized_adaptive_width_stops_at_15_pixels():
    from types import SimpleNamespace
    from efospec.local_sky import exposure_sky_inputs
    from efospec.recipes import DetectorWindow
    trace=np.full(40,35.)
    exposure=SimpleNamespace(window=DetectorWindow((40,85),(0,0)),
        images={'found_traces':np.array([trace,trace+40])})
    recipe={'objects':[dict(spec=20.,spat=35.,radius=7.,fwhm=4.)],
            'sky':dict(mode='pypeit_local',include=[],exclude=[],width_pixels=30,minimum_width_pixels=15)}
    mask,selected,info=exposure_sky_inputs(exposure,recipe)
    assert 15<=info['actual_width_spatial_pixels']<30
    assert np.all(side_counts(mask,selected,7.)==info['actual_width_spatial_pixels'])


def curved_background():
    y, x = np.indices((160, 180))
    trace = 89.+.01*(np.arange(160)-80.)
    true_sky = 250.+1.2*(x-89)+.028*(x-89)**2+60.*np.exp(-.5*((y-70.)/3.)**2)
    source = 3000.*np.exp(-.5*((x-trace[:, None])/1.7)**2)
    rng = np.random.default_rng(316)
    variance = true_sky+source+7.8**2
    data = true_sky+source+rng.normal(size=x.shape)*np.sqrt(variance)
    mask, _ = nearby_mask(data.shape, trace, radius=7., fwhm=4., width_pixels=35)
    data[62, 55] += 10000.
    tilts = (y+.004*x)/(159+.004*179)
    return data, variance, tilts, mask, trace, true_sky


def test_quadratic_pypeit_model_recovers_curved_background_and_rejects_cosmic():
    data, variance, tilts, mask, trace, truth = curved_background()
    fit = fit_background(data, 1/variance, tilts, mask, trace, radius=7., degree=2)
    center = np.round(trace).astype(int)
    rows = np.arange(15, 145)
    error = fit['sky'][rows, center[rows]]-truth[rows, center[rows]]
    assert abs(np.median(error)) < 2.
    assert np.sqrt(np.mean(error**2)) < 5.
    assert not fit['accepted_mask'][62, 55]
    assert not fit['accepted_mask'][~mask].any()
    assert np.all(fit['side_counts'][:, fit['valid_rows']] >= 5)
    assert fit['summary']['legendre_terms'] == 3
    assert fit['summary']['pypeit_exit_status'] == 0
    assert fit['summary']['constant_fallback'] is False


def test_one_sided_mask_rejected_before_fit():
    data, variance, tilts, mask, trace, _ = curved_background()
    mask[:, 90:] = False
    with pytest.raises(BackgroundSupportError, match='each side'):
        fit_background(data, 1/variance, tilts, mask, trace, radius=7.)


def test_nonconvergence_never_changes_polynomial_order(monkeypatch):
    from pypeit.core import fitting
    calls = []
    def failed(*args, **kwargs):
        calls.append(kwargs['basis'].shape)
        return None, np.ones_like(args[0], bool), np.zeros_like(args[0]), 1., 1
    monkeypatch.setattr(fitting, 'iterative_bspline_fit', failed)
    data, variance, tilts, mask, trace, _ = curved_background()
    with pytest.raises(BackgroundSupportError, match='no lower-order fallback'):
        fit_background(data, 1/variance, tilts, mask, trace, radius=7., degree=2)
    assert len(calls) == 1


def test_rejection_removing_one_side_stops_extraction(monkeypatch):
    from pypeit.core import fitting
    def one_sided(*args, **kwargs):
        accepted = kwargs['gpm'].copy()
        # The second Legendre term encodes the spatial coordinate.
        accepted &= kwargs['basis'][:, 1] < 0
        return None, accepted, np.ones_like(args[0]), 1., 0
    monkeypatch.setattr(fitting, 'iterative_bspline_fit', one_sided)
    data, variance, tilts, mask, trace, _ = curved_background()
    with pytest.raises(BackgroundSupportError, match='after rejection'):
        fit_background(data, 1/variance, tilts, mask, trace, radius=7., degree=2)


def test_pypeit_optimal_extraction_holds_bounded_quadratic_model(tmp_path):
    from astropy.io import fits
    from test_pypeit_adapter import write_raw
    from efospec.pypeit_adapter import EFOSpecEFOSC2Spectrograph
    from efospec.extraction import extract_spectra
    data, variance, tilts, mask, trace, truth = curved_background()
    raw = write_raw(tmp_path,'raw.fits')
    with fits.open(raw) as hdus:
        detector = EFOSpecEFOSC2Spectrograph().get_detector_par(1,hdus)
    (tmp_path/'QA/PNGs').mkdir(parents=True)
    result = extract_spectra(data, 5000.+800.*tilts, detector,
        exposure_time=600., read_noise=7.8, output=tmp_path, basename='local-quadratic',
        manual=[dict(id='primary',spec=80.,spat=89.,fwhm=4.,radius=7.)],
        sky_input_mask=mask, sky_trace=trace, sky_model={'degree':2,'sigma_clip':4.})
    obj = result['objects']['primary'][0]
    rows = obj.OPT_MASK & (np.arange(len(data))>25) & (np.arange(len(data))<135)
    assert rows.sum() > 90
    true_flux = 3000.*np.sqrt(2*np.pi)*1.7
    assert abs(np.median(obj.OPT_COUNTS[rows])/true_flux-1) < .02
    assert result['sky_policy'] == 'bounded_two_sided_pypeit'
    assert result['background_fit']['spatial_degree'] == 2
    assert not result['selection']['sky_accepted_mask'][~mask].any()
    # A later full-slit/constant refit would erase the strong curvature.
    y,x = np.indices(data.shape)
    aperture = (abs(x-trace[:,None])<7) & rows[:,None]
    assert abs(np.median(result['arrays'][0][aperture]-truth[aperture])) < 3.


def test_automatic_bounded_default_recovers_flux_without_full_slit_fit(tmp_path,monkeypatch):
    from astropy.io import fits
    from test_pypeit_adapter import write_raw
    from test_extraction import synthetic_image
    from efospec.pypeit_adapter import EFOSpecEFOSC2Spectrograph
    from efospec.extraction import extract_spectra
    from pypeit.core import skysub
    def forbidden(*args,**kwargs):raise AssertionError('full-slit global sky called')
    monkeypatch.setattr(skysub,'global_skysub',forbidden)
    data,wave,truth=synthetic_image()
    raw=write_raw(tmp_path,'raw.fits')
    with fits.open(raw) as hdus:detector=EFOSpecEFOSC2Spectrograph().get_detector_par(1,hdus)
    (tmp_path/'QA/PNGs').mkdir(parents=True)
    result=extract_spectra(data,wave,detector,exposure_time=600.,read_noise=7.8,
        output=tmp_path,basename='bounded-auto',target_position=48.,bounded_background=True)
    obj=result['objects']['primary'][0];rows=obj.OPT_MASK&(np.arange(160)>25)&(np.arange(160)<135)
    assert abs(np.median(obj.OPT_COUNTS[rows]/truth['primary'][rows])-1)<.02
    assert 15<=result['background_fit']['selection']['actual_width_spatial_pixels']<=30
