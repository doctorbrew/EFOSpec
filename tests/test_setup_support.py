"""Calibrations being present must never silently enable a new science route."""
from copy import deepcopy

import pytest

from efospec.native_readiness import assess_native_readiness
from efospec.rapid import UnsupportedSetupError, select_archive
from test_planning import frame, report


@pytest.mark.parametrize('grism,filter_name,paired,requirement', [
    ('Gr16', 'OG530', 'not_enabled', '5577 A'),
    ('Gr13', 'GG495', 'experimental', 'Free/GG495'),
])
def test_complete_inputs_still_explain_unsupported_science_route(
        tmp_path, grism, filter_name, paired, requirement):
    target = frame()
    target['setup'].update(grism=grism, filter=filter_name)
    inputs = [target]
    for role, count in [('arc', 1), ('bias', 3), ('flat', 3), ('standard_candidate', 1)]:
        for i in range(count):
            candidate = frame(f'{role}{i}', role)
            candidate['setup'] = deepcopy(target['setup'])
            candidate['metadata']['OBJECT'] = role
            inputs.append(candidate)
    assessment = assess_native_readiness(report(inputs))
    assert assessment['raw_candidates_complete']
    assert not assessment['reduction_ready']
    support = assessment['exposures'][0]['pipeline_support']
    assert support['native_masters'] == 'experimental'
    assert support['native_pair'] == paired
    assert not support['scientifically_validated']
    assert requirement in ' '.join(support['development_required'])
    with pytest.raises(UnsupportedSetupError) as caught:
        select_archive(target, tmp_path)
    assert caught.value.support == support
    assert f'{grism}/{filter_name}' in str(caught.value)
    assert requirement in caught.value.action


def test_uninspected_detector_mode_is_not_reported_as_native_supported(tmp_path):
    target = frame()
    target['setup'].update(binx=1)
    with pytest.raises(UnsupportedSetupError) as caught:
        select_archive(target, tmp_path)
    assert '2x2' in str(caught.value)
    assert caught.value.support['native_masters'] == 'not_enabled'
    assert caught.value.support['native_pair'] == 'not_enabled'
