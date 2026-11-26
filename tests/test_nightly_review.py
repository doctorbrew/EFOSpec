import pytest
from efospec.nightly_review import validation_policy, search_review


def test_nightly_uses_full_sky_and_preserves_explicit_review_policy():
    assert validation_policy(None)=='full-spectrum'
    assert validation_policy({'validation_policy':'three-line'})=='three-line'
    assert validation_policy({'validation_policy':'full-spectrum'})=='full-spectrum'
    assert validation_policy({'validation_policy':'two-anchor'})=='two-anchor'
    with pytest.raises(ValueError):validation_policy({'validation_policy':'ignore'})


def test_fixed_review_never_starts_dynamic_search():
    arguments={'manual':[{'spat':50}]}
    actual,evidence=search_review({},None,None,None,None,None,arguments,None)
    assert actual is arguments and evidence is None
