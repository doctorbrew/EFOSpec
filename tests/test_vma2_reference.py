import numpy as np
import pytest
from efospec.vma2_reference import parse_table, position_at, reference


def test_mjy_to_flambda_preserves_physical_density():
    air, flux = parse_table('SET .Z.UNITS = "mjy"\n5000 1\n10000 1\n')
    np.testing.assert_allclose(flux, [1.199169832e-15, 2.99792458e-16], rtol=1e-10)
    assert air.tolist() == [5000, 10000]
    with pytest.raises(ValueError, match='mJy'):
        parse_table('5000 1\n10000 1')
    with pytest.raises(ValueError, match='invalid'):
        parse_table('SET .Z.UNITS = "mjy"\n5000 1\n4000 1')


def test_motion_and_real_pointing_match_but_name_does_not(tmp_path):
    from astropy.coordinates import SkyCoord
    from astropy import units as u
    from astropy.time import Time
    mjd = Time('2026-10-30').mjd
    position = position_at(mjd)
    assert position.separation(SkyCoord(12.305284*u.deg, 5.36863*u.deg)).arcsec < 25
    assert position.separation(position_at(51544.5)).arcsec > 75
    assert reference({'metadata':{'OBJECT':'vma2', 'RA':180., 'DEC':0., 'MJD-OBS':mjd}}, tmp_path) is None
    assert not list(tmp_path.iterdir())


def test_changed_cached_reference_is_rejected(tmp_path):
    p = position_at(61000.)
    (tmp_path/'vma2-oke1974-ing.tab').write_text('changed')
    with pytest.raises(ValueError, match='reference changed'):
        reference({'metadata':{'RA':p.ra.deg,'DEC':p.dec.deg,'MJD-OBS':61000.}},tmp_path)
