"""Target markers require named target coordinates and an accepted image solution."""
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

from efospec.acquisition_target import target_coordinates, target_position, draw_target_position
from efospec.inventory import sha256


def target_header():
    return fits.Header({'RA':17., 'DEC':40., 'RADECSYS':'FK5',
        'ESO OBS TARG NAME':'SNtest', 'ESO TEL TARG COORDTYPE':'M',
        'ESO TEL TARG EQUINOX':2000., 'ESO TEL TARG ALPHA':235959.76,
        'ESO TEL TARG DELTA':-3028.5})


def test_target_is_ob_coordinate_not_offset_pointing_and_handles_negative_zero():
    h=target_header()
    result=target_coordinates(h,'SNtest')
    assert result['status']=='coordinates_available'
    assert result['ra_deg']==pytest.approx(359.999)
    assert result['dec_deg']==pytest.approx(-(.5+28.5/3600))
    assert result['ra_hms']=='23:59:59.76' and result['dec_dms']=='-00:30:28.50'
    assert not result['independent_catalogue_verification']
    assert target_coordinates(h,'SNanother')['status']=='coordinates_unavailable'
    del h['ESO TEL TARG ALPHA']
    assert target_coordinates(h,'SNtest')['status']=='coordinates_unavailable'


@pytest.mark.parametrize('key,value',[('ESO TEL TARG ALPHA',240000.),
    ('ESO TEL TARG DELTA',126000.),('ESO TEL TARG ALPHA',np.nan),
    ('ESO TEL TARG COORDTYPE','A'),('RADECSYS','FK4')])
def test_invalid_or_unsupported_coordinate_is_not_marked(key,value):
    h=target_header()
    # FITS forbids NaN header values, so use an ordinary mapping here.
    h=dict(h);h[key]=value
    assert target_coordinates(h,'SNtest')['status']=='coordinates_unavailable'


def fixture_solution(tmp_path):
    h=target_header();raw=tmp_path/'acq.fits'
    fits.writeto(raw,np.zeros((120,160)),h)
    target=target_coordinates(h,'SNtest')
    w=WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN']
    w.wcs.crval=target['icrs_deg'];w.wcs.crpix=[66.,41.]
    w.wcs.cd=np.array([[0.,-.24/3600],[.24/3600,0.]])
    wcs=tmp_path/'solution.wcs';fits.PrimaryHDU(header=w.to_header()).writeto(wcs)
    x=np.arange(10,110,10.);y=np.array([20.,90.]*5);sky=w.pixel_to_world(x,y)
    corr=tmp_path/'solution.corr'
    Table({'field_x':x+1,'field_y':y+1,'index_ra':sky.ra.deg,'index_dec':sky.dec.deg,
           'match_weight':np.ones(10)}).write(corr,format='fits')
    solution={'status':'solved','raw':str(raw),'raw_sha256':sha256(raw),
        'wcs':str(wcs),'wcs_sha256':sha256(wcs),
        'correspondences':str(corr),'correspondences_sha256':sha256(corr)}
    return raw,solution


def test_marker_uses_rotated_wcs_zero_based_pixels_and_leaves_source_centre_open(tmp_path):
    import matplotlib.pyplot as plt
    raw,solution=fixture_solution(tmp_path)
    before=sha256(raw)
    result=target_position(raw,'SNtest',solution)
    assert result['status']=='projected'
    assert result['pixel_xy']==pytest.approx([65.,40.],abs=1e-6)
    fig,axes=plt.subplots(1,2)
    for ax in axes:ax.set(xlim=(-.5,159.5),ylim=(-.5,119.5))
    draw_target_position(axes,result)
    for ax in axes:
        marker,=ax.collections
        np.testing.assert_allclose(marker.get_offsets()[0],[65.,40.],atol=1e-6)
        assert len(marker.get_facecolors())==0
        assert ax.texts[0].get_text()=='SNtest'
    assert sha256(raw)==before
    plt.close(fig)


def test_missing_wcs_shows_coordinates_without_inventing_centre(tmp_path):
    import matplotlib.pyplot as plt
    raw,_=fixture_solution(tmp_path)
    result=target_position(raw,'SNtest')
    assert result['status']=='unregistered' and 'pixel_xy' not in result
    fig,axes=plt.subplots(1,2);draw_target_position(axes,result)
    assert all(not ax.collections for ax in axes)
    assert 'Position not registered' in axes[0].artists[0].txt.get_text()
    plt.close(fig)


def test_astrometry_must_match_raw_and_pass_unchanged_residual_gates(tmp_path):
    raw,solution=fixture_solution(tmp_path)
    with pytest.raises(ValueError,match='different acquisition'):
        target_position(raw,'SNtest',dict(solution,raw_sha256='wrong'))
    corr=Path(solution['correspondences']);table=Table.read(corr)
    table['field_x']+=10;table.write(corr,format='fits',overwrite=True)
    with pytest.raises(ValueError,match='correspondences changed'):
        target_position(raw,'SNtest',solution)
    solution['correspondences_sha256']=sha256(corr)
    with pytest.raises(ValueError,match='residuals'):
        target_position(raw,'SNtest',solution)
