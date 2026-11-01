import numpy as np
import pytest


def sky_image(include_check=True):
    rng=np.random.default_rng(42)
    w=np.linspace(3600.,9300.,1024)
    wave=w[:,None]+np.linspace(-2,2,141)[None,:]
    image=np.full(wave.shape,120.)
    for rest,amp in [(5577.338,1200.),(6300.304,600.),(6363.776,200. if include_check else 0.)]:
        image+=amp*np.exp(-.5*((wave-(rest+6.))/7.5)**2)
    return image+rng.normal(0,8,image.shape),wave


def test_held_out_6363_fit_is_not_seeded_by_stronger_6300_wing():
    from efospec.native_sky import measure_flexure
    image,wave=sky_image()
    shift,qa=measure_flexure(image,wave)
    assert shift==pytest.approx(-6.,abs=.2)
    assert qa['held_out_6363_pass']
    assert abs(qa['held_out_6363_residual_angstrom'])<.3


def test_missing_independent_sky_line_stops_native_delivery():
    from efospec.native_sky import measure_flexure
    image,wave=sky_image(False)
    with pytest.raises(ValueError,match='6363'):measure_flexure(image,wave)
