from copy import deepcopy
from efospec.report_evidence import background_evidence, calibration_overview, response_status


def test_automatic_background_is_present_without_manual_experiments():
    run=dict(results=[dict(object='SNtest',grism='Gr13',processing=dict(background_fit=dict(
        pypeit_exit_status=0,spatial_degree=2,minimum_side_samples=19,invalid_rows=[2],reduced_chi2=1.2,
        selection=dict(actual_width_spatial_pixels=25,automatic_background_selection=dict(geometry_unresolved=True)))))],
        errors=[dict(code='background_support_required',object='SNfailed')])
    before=deepcopy(run);html=background_evidence(run)
    assert 'SNtest' in html and 'Fit converged' in html and '<td>25</td>' in html and '<td>19</td>' in html
    assert 'Default retained; comparison unavailable' in html and '1 exposures remain blocked' in html
    assert 'No retained polynomial' not in html and run==before


def test_missing_background_record_is_not_called_a_success():
    html=background_evidence(dict(results=[dict(object='Unknown')]))
    assert 'Background evidence unavailable' in html and 'Fit converged' not in html
    assert 'No extracted products' in background_evidence({})


def test_counts_background_stays_distinct_from_validated_flux():
    html=background_evidence(dict(review_counts=[dict(object='Counts',setup=dict(grism='Gr16'),
        background=dict(pypeit_exit_status=0,spatial_degree=2,minimum_side_samples=15,invalid_rows=[]))]))
    assert 'Review counts' in html and 'Gr16' in html and 'Flux product' not in html


def test_calibration_construction_and_validation_are_separate():
    fit=dict(status='response_built_unvalidated',response={'path':'response.fits'})
    run=dict(standards=[dict(fit=fit)],results=[dict(role='science',processing=dict(bias=True,flat=True))],
        independent_flux_validation=False,limitations=['Standards retain arc-only wavelengths.'],
        held_out_errors=[dict(training_raw='/raw/a.fits',test_raw='/raw/b.fits',error='No valid samples')])
    html=calibration_overview(run)
    assert '1 response functions' in html and '1 science flux products' in html
    assert 'Independent absolute accuracy unvalidated' in html and 'arc-only wavelengths' in html
    assert 'Failed response-transfer checks' in html and 'No valid samples' in html
    assert 'Response built' in response_status(fit) and 'accuracy unvalidated' in response_status(fit)
    assert 'No correction-scope record' in calibration_overview({})
