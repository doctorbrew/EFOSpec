import json
from types import SimpleNamespace

import numpy as np
import pytest

from efospec.profile_background import summed_profile, load_profile_background


def test_sum_uses_same_complete_rows_without_filling_missing_pixels():
    residual = np.array([[1., 5., np.nan], [2., 6., 8.], [9., 20., 30.]])
    values, used = summed_profile(residual, np.arange(3), [True,True,False])
    np.testing.assert_array_equal(values, [2.,6.,8.])
    assert used == 1
    values, used = summed_profile(residual, np.arange(3), [False]*3)
    assert np.isnan(values).all() and used == 0


def test_profile_uses_only_displayed_support_and_keeps_dead_columns_missing():
    residual = np.array([[np.nan, 1., 10., np.nan, 100.],
                         [np.nan, 2., np.nan, np.nan, 200.],
                         [np.nan, 3., 30., np.nan, 300.]])
    values, used = summed_profile(residual, np.arange(3), [True]*3,
                                  spatial_columns=[False,True,True,True,False])
    np.testing.assert_array_equal(values, [np.nan,4.,40.,np.nan,np.nan])
    assert used == 2


def test_profile_with_no_common_valid_rows_stays_missing():
    values, used = summed_profile(np.array([[1.,np.nan],[np.nan,2.]]),
                                  np.arange(2), [True,True])
    assert np.isnan(values).all() and used == 0


def test_changed_saved_background_is_rejected_before_reuse(tmp_path):
    model = tmp_path/'run.json';model.write_text('{}')
    (tmp_path/'profile-background.json').write_text(json.dumps({
        'manifest':str(model), 'manifest_sha256':'wrong'}))
    with pytest.raises(ValueError, match='manifest changed'):
        load_profile_background(SimpleNamespace(),tmp_path)
