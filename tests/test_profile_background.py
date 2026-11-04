import json
from types import SimpleNamespace

import numpy as np
import pytest

from efospec.profile_background import summed_profile, load_profile_background


def test_sum_is_not_median_and_does_not_recenter_or_zero_missing_pixels():
    residual = np.array([[1., 5., np.nan], [2., 6., 8.], [9., 20., 30.]])
    values, used = summed_profile(residual, np.arange(3), [True,True,False])
    np.testing.assert_array_equal(values, [3.,11.,np.nan])
    assert used == 2
    values, used = summed_profile(residual, np.arange(3), [False]*3)
    assert np.isnan(values).all() and used == 0


def test_changed_saved_background_is_rejected_before_reuse(tmp_path):
    model = tmp_path/'run.json';model.write_text('{}')
    (tmp_path/'profile-background.json').write_text(json.dumps({
        'manifest':str(model), 'manifest_sha256':'wrong'}))
    with pytest.raises(ValueError, match='manifest changed'):
        load_profile_background(SimpleNamespace(),tmp_path)
