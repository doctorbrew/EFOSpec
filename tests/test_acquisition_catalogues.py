"""Catalogue coordinates, ambiguous counterparts and astrometric acceptance."""
from io import BytesIO
import json
from pathlib import Path

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

from efospec.acquisition_astrometry import check_solution
from efospec.field_catalogues import fetch_catalogue, parse_catalogue, project_sources, query_spec


def celestial():
    w = WCS(naxis=2)
    w.wcs.ctype=['RA---TAN','DEC--TAN']; w.wcs.crval=[359.999, -30.]
    w.wcs.crpix=[51.,51.]; w.wcs.cd=np.array([[0., -.24/3600.],[-.24/3600., 0.]])
    return w


def test_host_overlay_excludes_unclassified_sources_and_preserves_redshift_methods(tmp_path,monkeypatch):
    from efospec.catalogue_plots import plot_catalogue_field
    from efospec.field_catalogues import redshift_label
    def source(label,galaxy,z,flag,cat='NED'):
        return {'id':label,'name':'Name '+label,'catalogue':cat,'galaxy_candidate':galaxy,'x':40.,'y':45.,
                'metadata':{'z':z,'zflag':flag}}
    rows=[source('N1',True,.0140230004,'SLS'),source('N2',True,.2,'PUN'),
          source('A3',False,None,'','AllWISE'),source('N4',False,None,'')]
    assert redshift_label(rows[0])=='z=0.014023 (spec)'
    assert redshift_label(rows[1])=='z=0.2 (phot)'
    assert redshift_label(source('N5',True,None,''))=='z unavailable'
    assert redshift_label(source('N6',True,.1,''))=='z=0.1 (method unknown)'
    assert redshift_label(source('N7',True,.1,'S1L?'))=='z=0.1 (spec; uncertain)'
    def inspect(fig,*args,**kwargs):
        from matplotlib.text import Text
        from matplotlib.transforms import Bbox
        fig.canvas.draw()
        renderer=fig.canvas.get_renderer()
        point=fig.dpi/72
        assert len(fig.legends)==1
        legend=fig.legends[0]
        assert legend.get_title().get_text()=='NED galaxy candidates'
        assert [t.get_text() for t in legend.get_texts()]==[
            'Galaxy 1: Name N1 [z=0.014023, SLS]','Galaxy 2: Name N2 [z=0.2, PUN]']
        for ax in fig.axes:
            assert ax.images[0].get_cmap().name=='gray_r'
            assert sum(len(c.get_offsets()) for c in ax.collections)==2
            labels=[t.get_text() for t in ax.texts]
            assert labels==['Galaxy 1','Galaxy 2']
            assert all(t.get_bbox_patch().get_facecolor()==(1.,1.,1.,.8) for t in ax.texts)
            assert ax.get_legend() is None
            assert not ax.get_legend_handles_labels()[1]
            boxes=[]
            for label in ax.texts:
                box=Text.get_window_extent(label,renderer).padded(2*point)
                x,y=ax.transData.transform(label.xy)
                assert box.x1 < x-8*point or box.x0 > x+8*point
                assert ax.bbox.contains(box.x0,box.y0) and ax.bbox.contains(box.x1,box.y1)
                assert not any(box.overlaps(other) for other in boxes)
                for collection in ax.collections:
                    for xy in collection.get_offsets():
                        mx,my=ax.transData.transform(xy)
                        assert not box.overlaps(Bbox.from_extents(mx-8*point,my-8*point,mx+8*point,my+8*point))
                boxes.append(box)
                from efospec.acquisition_display import TEXT_COLORS
                assert label.get_color() == TEXT_COLORS['galaxy'] and not label.get_path_effects()
    monkeypatch.setattr('efospec.catalogue_plots.save_qc',inspect)
    raw=tmp_path/'test.fits'
    fits.writeto(raw,np.ones((100,100)))
    plot_catalogue_field(np.ones((100,100)),{'object':'SN test','raw':str(raw),'sources':rows,
        'astrometry':{'matched_stars':10,'rms_pixel':.5}},tmp_path)


def votable(table):
    stream=BytesIO();table.write(stream,format='votable');return stream.getvalue()


def test_ned_coordinates_types_and_missing_redshift():
    table=Table({'prefname':['Galaxy','Infrared'], 'ra':[10.,11.], 'dec':[-30.,-30.],
                 'ptype':['G',''], 'z':[.01,np.nan], 'zflag':['S','']})
    rows=parse_catalogue(votable(table),'NED')
    assert rows[0]['galaxy_candidate'] and not rows[1]['galaxy_candidate']
    assert rows[1]['metadata']['z'] is None
    expected=SkyCoord(10*u.deg,-30*u.deg,frame='fk5').icrs
    assert rows[0]['ra']==pytest.approx(expected.ra.deg,abs=1e-10)
    assert all(not r['host_confirmed'] for r in rows)
    _,params,_=query_spec('NED',10.,-30.,3.)
    assert params['LON']=='10.0000000000d' and params['RADIUS']==3.


def test_wise_extended_flags_do_not_confirm_a_galaxy_or_host():
    t=Table({'designation':['Jtest'], 'ra':[10.], 'dec':[-30.],
             'w1mpro':[12.], 'w2mpro':[11.], 'ext_flg':[5], 'cc_flags':['0000']})
    row=parse_catalogue(votable(t),'AllWISE')[0]
    assert row['metadata']['ext_flg']==5 and not row['galaxy_candidate'] and not row['host_confirmed']


def test_sdss_identifiers_remain_exact_and_morphology_is_not_host_identity():
    rows=parse_catalogue(b'#Table1\nobjid,ra,dec,type,modelMag_r\n1237667430104694861,10,-30,3,18.2\n1237667430104694862,10.1,-30,6,15.1\n','SDSS')
    assert rows[0]['name']=='1237667430104694861' and rows[0]['galaxy_candidate']
    assert not rows[1]['galaxy_candidate'] and not rows[0]['host_confirmed']
    with pytest.raises(ValueError,match='response columns'):
        parse_catalogue(b'error\nservice down\n','SDSS')


def test_service_errors_are_not_empty_successes(tmp_path,monkeypatch):
    class Response:
        status_code=200
        content=b'<VOTABLE><RESOURCE><INFO name="QUERY_STATUS" value="ERROR">bad query</INFO></RESOURCE></VOTABLE>'
        def raise_for_status(self):pass
    monkeypatch.setattr('efospec.field_catalogues.requests.get',lambda *a,**k:Response())
    result=fetch_catalogue('NED',[10.,-30.],3.,tmp_path)
    assert result['status']=='unavailable' and result['rows']==[] and 'bad query' in result['error']
    # Retained errors remain errors offline; changed raw responses are refused.
    monkeypatch.setattr('efospec.field_catalogues.requests.get',lambda *a,**k:pytest.fail('unexpected network'))
    assert fetch_catalogue('NED',[10.,-30.],3.,tmp_path)==result
    (tmp_path/result['response']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='response changed'):fetch_catalogue('NED',[10.,-30.],3.,tmp_path)


def test_rotated_wcs_wraps_ra_and_retains_ambiguous_cross_catalogue_matches():
    w=celestial()
    def row(cat,name,x,y,galaxy=False):
        s=w.pixel_to_world(x,y).icrs
        return {'catalogue':cat,'name':name,'ra':s.ra.deg,'dec':s.dec.deg,
                'galaxy_candidate':galaxy,'host_confirmed':False,'metadata':{}}
    queries=[{'rows':[row('NED','g',50,50,True)]},
             {'rows':[row('AllWISE','a',52,50),row('AllWISE','b',48,50),row('AllWISE','outside',101,50)]}]
    rows=project_sources(queries,w,(100,100))
    assert len(rows)==3
    g=rows[0]; assert g['x']==pytest.approx(50) and g['y']==pytest.approx(50)
    assert len(g['positional_neighbours'])==2
    assert all(n['separation_arcsec']==pytest.approx(.48,abs=.001) for n in g['positional_neighbours'])
    assert all(not r['host_confirmed'] for r in rows)


def test_astrometric_solution_checks_fits_origin_residuals_and_minimum_matches(tmp_path):
    w=celestial(); path=tmp_path/'solution.wcs';fits.PrimaryHDU(header=w.to_header()).writeto(path)
    x=np.linspace(15,85,10);y=np.array([20,70]*5)
    sky=w.pixel_to_world(x,y)
    table=Table({'field_x':x+1,'field_y':y+1,'index_ra':sky.ra.deg,'index_dec':sky.dec.deg,'match_weight':np.ones(10)})
    corr=tmp_path/'match.corr';table.write(corr,format='fits')
    _,quality=check_solution(path,corr,(100,100))
    assert quality['rms_pixel']<1e-6 and quality['matched_stars']==10
    assert quality['independent_astrometric_validation'] is False
    table['field_x']+=10;table.write(corr,format='fits',overwrite=True)
    with pytest.raises(ValueError,match='residuals'):check_solution(path,corr,(100,100))
    table[:7].write(corr,format='fits',overwrite=True)
    with pytest.raises(ValueError,match='eight'):check_solution(path,corr,(100,100))


def test_successful_empty_query_and_wrong_cached_cone(tmp_path,monkeypatch):
    class Response:
        status_code=200
        content=b'objid,ra,dec,type,modelMag_r\n'
        def raise_for_status(self):pass
    monkeypatch.setattr('efospec.field_catalogues.requests.get',lambda *a,**k:Response())
    result=fetch_catalogue('SDSS',[10.,-30.],3.,tmp_path)
    assert result['status']=='no_matches' and not result['rows']
    with pytest.raises(ValueError,match='query differs'):fetch_catalogue('SDSS',[11.,-30.],3.,tmp_path)


def test_acquisition_qc_to_offline_report_preserves_raw_data_and_rejects_tampering(tmp_path,monkeypatch):
    from efospec.__main__ import main
    from efospec.acquisition_astrometry import solve_acquisition
    from efospec.epoch_report import build_epoch_page
    from efospec.inventory import sha256
    from PIL import Image
    from types import SimpleNamespace
    night='2026-10-29';root=tmp_path/'runs'/night;revision=root/'nightly/revision'
    rawdir=tmp_path/'data'/night;rawdir.mkdir(parents=True)
    revision.mkdir(parents=True);(revision/'reduction').mkdir()
    def save(p,value):p.write_text(json.dumps(value))
    save(root/'nightly/current.json',{'night':night,'revision':'revision'})
    save(revision/'night.json',{'night':night,'status':'partial'})
    header=fits.Header({'RA':359.999,'DEC':-30.,'OBJECT':'SN2026test','EXPTIME':30.,'DATE-OBS':'2026-10-30T01:00:00'})
    header['HIERARCH ESO OBS ID']=42
    header['HIERARCH ESO DET WIN1 BINX']=2;header['HIERARCH ESO DET WIN1 BINY']=2
    science=rawdir/'science.fits';fits.PrimaryHDU(np.zeros((100,100)),header=header).writeto(science)
    header['HIERARCH ESO TPL ID']='EFOSC_img_acq_MoveToSlit'
    acquisition=rawdir/'acquisition.fits';fits.PrimaryHDU(np.random.default_rng(2).normal(100,2,(100,100)),header=header).writeto(acquisition)
    frame={'path':str(science),'sha256':sha256(science),'role':'science',
           'metadata':dict(header),'setup':{'grism':'Gr13','filter':'Free','slit':'slit1.5'}}
    save(revision/'observing-log.json',{'frames':[frame]})
    save(revision/'reduction/run.json',{'results':[], 'errors':[], 'skipped':[{'path':str(science),'object':'SN2026test','reason':'test'}]})
    before={p:sha256(p) for p in rawdir.glob('*.fits')}
    w=celestial()
    # Emulate external solver outputs; the production residual acceptance runs.
    def solver(command,**kwargs):
        output=Path(command[command.index('--dir')+1])
        fits.PrimaryHDU(header=w.to_header()).writeto(output/'acquisition.wcs')
        x=np.linspace(15,85,10);y=np.array([20,70]*5);sky=w.pixel_to_world(x,y)
        Table({'field_x':x+1,'field_y':y+1,'index_ra':sky.ra.deg,'index_dec':sky.dec.deg,
               'match_weight':np.ones(10)}).write(output/'acquisition.corr',format='fits')
        (output/'acquisition.solved').write_bytes(b'1')
        return SimpleNamespace(returncode=0)
    sky=w.pixel_to_world(50,50)
    nedsky=sky.transform_to('fk5')
    ned=votable(Table({'prefname':['Test galaxy'],'ra':[nedsky.ra.deg],'dec':[nedsky.dec.deg],
                       'ptype':['G'],'z':[.01],'zflag':['S']}))
    wise=votable(Table({'designation':['IR source'],'ra':[sky.ra.deg],'dec':[sky.dec.deg],
                        'w1mpro':[12.],'w2mpro':[11.],'ext_flg':[0],'cc_flags':['0000']}))
    class Response:
        status_code=200
        def __init__(self,content):self.content=content
        def raise_for_status(self):pass
    def get(url,**kwargs):
        if 'skyserver' in url:raise TimeoutError('simulated SDSS service timeout')
        return Response(ned if 'ned.ipac' in url else wise)
    # The subprocess replacement is scoped to the solver; Matplotlib needs real TeX subprocesses.
    real_solve=solve_acquisition
    from unittest.mock import patch
    def scoped_solver(*args,**kwargs):
        with patch('efospec.acquisition_astrometry.shutil.which',return_value='/test/solve-field'), \
             patch('efospec.acquisition_astrometry.subprocess.run',side_effect=solver):
            return real_solve(*args,**kwargs)
    monkeypatch.setattr('efospec.acquisition_catalogues.solve_acquisition',scoped_solver)
    monkeypatch.setattr('efospec.field_catalogues.requests.get',get)
    out=root/'QC/catalogues-test'
    assert main(['acquisition-catalogues',night,'--project-root',str(tmp_path),'--output',str(out)])==1
    record=json.loads((out/'catalogues.json').read_text());field=record['fields'][0]
    assert field['status']=='partial' and field['queries'][1]['status']=='unavailable'
    assert field['astrometry']['rms_pixel']<1e-6
    assert len(field['sources'])==2 and len(field['sources'][0]['positional_neighbours'])==1
    assert all(sha256(p)==digest for p,digest in before.items())
    for p in (out/'acquisition').glob('*.jpg'):
        with Image.open(p) as im:assert im.info['dpi']==(300,300)
        assert p.with_suffix('.pdf').read_bytes().startswith(b'%PDF')
    build_epoch_page(night,tmp_path)
    html=(root/'index.html').read_text()
    assert 'Test galaxy' in html and 'Galaxy markers show catalogue-classified candidates' in html
    assert 'unavailable</span>' in html and 'Reduction Archive' in html
    assert '#records' not in html and 'data:image/webp;base64,' in html
    # The viewer-safe page embeds only a compact preview; the full-resolution
    # figure stays a sibling download and is embedded in the portable export.
    assert 'data:image/jpeg;base64,' not in html
    portable=(root/'index-portable.html').read_text()
    assert 'data:image/jpeg;base64,' in portable and 'data:application/pdf;base64,' in portable
    Path(field['astrometry']['wcs']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='WCS changed'):build_epoch_page(night,tmp_path)
