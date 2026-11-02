"""Known-offset spectra must survive displaced/blended sky-line windows."""
import numpy as np
import pytest
from efospec.archive_calibration import sky_flexure


def sky_image(shift, sigma=12., offsets=None, amplitudes=(500., 400., 133.)):
    wave = np.repeat(np.linspace(5200., 6700., 501)[:, None], 81, axis=1)
    data = np.full(wave.shape, 30.)
    for rest, amplitude, offset in zip((5577.338, 6300.304, 6363.776), amplitudes,
                                       offsets or (shift, shift, shift)):
        data += amplitude*np.exp(-.5*((wave-(rest-offset))/sigma)**2)
    data += np.random.default_rng(48).normal(0, .2, data.shape)
    return data, wave


@pytest.mark.parametrize('shift', [-60., -20., 0., 20., 37., 60.])
def test_broad_displaced_lines_recover_offset_and_check_line(shift):
    measured, qa = sky_flexure(*sky_image(shift))
    assert measured == pytest.approx(shift, abs=.1)  # 1/30 spectral pixel
    assert qa['held_out_6363_pass']
    assert abs(qa['held_out_6363_residual_angstrom']) < .1


def test_disagreeing_anchors_are_not_forced_to_agree():
    with pytest.raises(ValueError, match='cannot establish'):
        sky_flexure(*sky_image(20., offsets=(20., 29., 20.)))


def test_check_line_does_not_set_the_shift():
    measured, qa = sky_flexure(*sky_image(20., offsets=(20., 20., 30.)))
    assert measured == pytest.approx(20., abs=.1)
    assert not qa['held_out_6363_pass']
    assert qa['held_out_6363_residual_angstrom'] == pytest.approx(-10., abs=.1)


def test_single_strong_line_does_not_replace_two_anchor_requirement():
    with pytest.raises(ValueError, match='cannot establish'):
        sky_flexure(*sky_image(20., amplitudes=(500., 0., 0.)))


def test_failed_sky_retains_serializable_measurements_and_gate():
    import json
    from efospec.archive_calibration import SkyFlexureError
    with pytest.raises(SkyFlexureError) as caught:
        sky_flexure(*sky_image(20., offsets=(20., 29., 20.)))
    qa = caught.value.diagnostics
    assert 'anchor_disagreement' in qa['failed_gates']
    assert qa['anchor_difference_angstrom'] == pytest.approx(9., abs=.1)
    json.dumps(qa, allow_nan=False)


@pytest.mark.parametrize('shift,sigma', [(120., 12.), (20., 22.)])
def test_out_of_range_or_boundary_limited_lines_still_fail(shift, sigma):
    with pytest.raises(ValueError, match='cannot establish'):
        sky_flexure(*sky_image(shift, sigma))
