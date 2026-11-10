"""Daily response isolation and failure policy."""
from copy import deepcopy
from pathlib import Path
import pytest
from efospec.daily_reduction import select_response, matches
from efospec.inventory import sha256


def frame(mjd=61342.2):
    return dict(night='20261029', setup=dict(grism='Gr13',filter='Free',slit='slit1.5',
                binx=2,biny=2,readout='fastL'), metadata={'MJD-OBS':mjd})


def entry(tmp_path, mjd=61342.1):
    paths=[]
    for name in ('response','raw','extinction'):
        p=tmp_path/name;p.write_text(name);paths.append(p)
    response=dict(path=str(paths[0]),sha256=sha256(paths[0]), standard_raw=str(paths[1]),
                  standard_sha256=sha256(paths[1]),extinction=dict(path=str(paths[2]),sha256=sha256(paths[2])))
    return dict(frame=frame(mjd),fit=dict(status='response_built_unvalidated',response=response))


@pytest.mark.parametrize('key,value', [('filter','GG495'),('grism','Gr11'),('slit','slit1.0'),
    ('binx',1),('biny',1),('readout','slow')])
def test_no_cross_setup_response(tmp_path,key,value):
    std=entry(tmp_path); std['frame']['setup'][key]=value
    with pytest.raises(ValueError,match='no successful same-night'):
        select_response(frame(),[std])


def test_same_night_required_even_for_nearby_mjd(tmp_path):
    std=entry(tmp_path);std['frame']['night']='20261028'
    with pytest.raises(ValueError,match='no successful same-night'):select_response(frame(),[std])


def test_failed_response_is_not_selected_and_ties_fail(tmp_path):
    std=entry(tmp_path);other=deepcopy(std);other['fit']['status']='response_failed'
    other['frame']['metadata']['MJD-OBS']=61342.2
    assert select_response(frame(),[other,std]) is std
    other['fit']['status']='response_built_unvalidated'
    other['frame']['metadata']['MJD-OBS']=61342.3
    with pytest.raises(ValueError,match='tied'):select_response(frame(),[std,other])


@pytest.mark.parametrize('filename',['response','raw','extinction'])
def test_changed_inputs_cannot_be_applied(tmp_path,filename):
    std=entry(tmp_path);(tmp_path/filename).write_text('changed')
    with pytest.raises(ValueError,match='changed'):select_response(frame(),[std])

from test_native_end_to_end import synthetic_raw_night


def test_daily_raw_photons_preserve_flux_scale_and_include_unrequested_standard(
        synthetic_raw_night,tmp_path,monkeypatch):
    import builtins
    import io
    import numpy as np
    from astropy import units as u
    from astropy.io import fits
    from efospec import standard_reference
    from efospec.daily_reduction import reduce_daily
    root,science,standard=synthetic_raw_night
    wave=np.arange(3000.,11001.,2.)
    def physical(frame,cache):
        return dict(name='SyntheticStandard',std_ra=0.,std_dec=0.,cal_file='synthetic-truth',
            std_source='test_photons',wave=wave*u.AA,
            flux=np.full(wave.shape,1000.)*u.erg/u.s/u.cm**2/u.AA)
    monkeypatch.setattr(standard_reference,'standard_reference',physical)
    def guard(original):
        def guarded(file,*args,**kwargs):
            if isinstance(file,(str,Path)) and any(s in str(file) for s in ('trunk/src/ntt','/archive/efosc','/database/')):
                raise AssertionError('daily route attempted to read archived calibration')
            return original(file,*args,**kwargs)
        return guarded
    monkeypatch.setattr(builtins,'open',guard(builtins.open))
    monkeypatch.setattr(io,'open',guard(io.open))
    run=reduce_daily(root,tmp_path/'daily',night='2024-11-14',targets=['SyntheticSN'])
    assert run['execution_status']=='complete', run['errors']
    assert len(run['standards'])==1 and len(run['results'])==2
    result=next(r for r in run['results'] if r['role']=='science')
    assert result['sky_flexure']['held_out_6363_pass']
    assert result['processing']['bias'] and result['processing']['flat']
    assert result['sensitivity']['standard_raw']==str(standard)
    assert result['sensitivity']['night']=='2024-11-14'
    with fits.open(result['product']) as h:
        assert h[0].header['FLUXCAL']=='NATIVE' and h[0].header['WAVEMED']=='air'
        good=h['VALID'].data[0].astype(bool)
        # Known independent photon rate ratio: 3000/1200 versus 20000/100.
        assert np.median(h[0].data[0,0,good])/1.25e-16==pytest.approx(1.,rel=.08)
        assert np.all(np.isfinite(h[0].data[3,0,good]) & (h[0].data[3,0,good]>0))
    assert not run['held_out'] and not run['independent_flux_validation']
    with pytest.raises(FileExistsError):
        reduce_daily(root,tmp_path/'daily',night='2024-11-14',targets=['SyntheticSN'])


def test_failed_standard_prevents_science_export_without_archive_fallback(
        synthetic_raw_night,tmp_path,monkeypatch):
    from efospec import daily_reduction
    root,science,standard=synthetic_raw_night
    attempted=[]
    def fail(frame,*args,**kwargs):
        attempted.append(frame['path'])
        raise ValueError('standard background geometry rejected')
    monkeypatch.setattr(daily_reduction,'prepare',fail)
    run=daily_reduction.reduce_daily(root,tmp_path/'failed',night='2024-11-14',targets=['SyntheticSN'])
    assert attempted==[str(standard)]
    assert not run['results'] and not run['standards']
    assert run['execution_status']=='failed'
    assert len(run['errors'])==2
    assert run['errors'][1]['stage']=='response_selection'
    assert 'no successful same-night' in run['errors'][1]['error']
    assert not list((tmp_path/'failed/products').iterdir())


def test_failed_science_wavelengths_retain_only_explicit_review_counts(synthetic_raw_night,tmp_path,monkeypatch):
    import numpy as np
    from astropy import units as u
    from astropy.io import fits
    from efospec import daily_reduction
    from efospec.native_sky import SkyValidationError
    original=daily_reduction.prepare
    def missing_check(frame,*args,**kwargs):
        if frame['role']=='science' and not kwargs.get('arc_only_review'):
            raise SkyValidationError('independent 6363 line absent',[])
        return original(frame,*args,**kwargs)
    monkeypatch.setattr(daily_reduction,'prepare',missing_check)
    wave=np.arange(3000.,11001.,2.)
    monkeypatch.setattr('efospec.standard_reference.standard_reference',lambda *args:
        dict(name='SyntheticStandard',cal_file='synthetic-truth',std_source='test_photons',
             wave=wave*u.AA,flux=np.full(wave.shape,1000.)*u.erg/u.s/u.cm**2/u.AA))
    root,science,standard=synthetic_raw_night
    run=daily_reduction.reduce_daily(root,tmp_path/'review',night='2024-11-14',targets=['SyntheticSN'])
    assert len(run['errors'])==1 and len(run['review_counts'])==1
    assert all(r['role']=='standard_candidate' for r in run['results'])
    counts=run['review_counts'][0]
    assert not counts['flux_calibrated'] and not counts['science_validated']
    assert counts['sky_flexure']['shift_angstrom']==0.
    assert counts['sky_flexure']['held_out_6363_pass'] is False
    with fits.open(counts['product']) as hdus:
        assert hdus[0].header['FLUXCAL']=='NONE'
        assert hdus[0].header['BUNIT']=='electron'
    assert not run['review_counts_errors']
    # Explicit rescue preserves the failed parent and labels FITS/ASCII output.
    from efospec.rescue import rescue_daily
    from efospec.report import reduction_methods
    parent=tmp_path/'review';before=sha256(parent/'run.json')
    original_count=sha256(Path(counts['product']))
    for primary in ('optimal','boxcar'):
        rescued=rescue_daily(parent,tmp_path/('rescue-'+primary),night='2024-11-14',
            boxcar_targets=['SyntheticSN'] if primary=='boxcar' else [])
        assert not rescued['errors'],rescued['errors']
        result=rescued['results'][0]
        assert result['status']=='PROVISIONAL' and not result['wavelength_validated']
        assert result['primary_extraction']==primary
        assert result['sky_flexure']['shift_angstrom']==0
        assert not result['sky_flexure']['held_out_6363_pass']
        with fits.open(result['product'],checksum=True) as hdus:
            h=hdus[0].header;good=hdus['VALID'].data[0].astype(bool)
            assert h['EPSTATUS']=='PROVISIONAL' and h['WAVEVAL'] is False
            assert h['FLXVALID'] is False and h['WAVSHIFT']==0
            assert h['EXTRPRI']==primary.upper() and h['BANDID1']==primary+' flux'
            assert h['BANDID4']==primary+' flux uncertainty'
            assert np.median(hdus[0].data[0,0,good])/1.25e-16==pytest.approx(1.,rel=.08)
            assert np.all(np.isfinite(hdus[0].data[3,0,good]) & (hdus[0].data[3,0,good]>0))
            assert all(x.verify_checksum()==1 and x.verify_datasum()==1 for x in hdus)
        assert 'PROVISIONAL' in Path(result['product']).with_suffix('.asci').read_text().splitlines()[0]
        stages,summary,_=reduction_methods(rescued)
        assert 'PROVISIONAL' in summary
        assert 'no flexure correction' in next(d for s,_,d in stages if s=='Wavelength calibration')
    assert sha256(parent/'run.json')==before
    assert sha256(Path(counts['product']))==original_count
    Path(counts['ascii']).write_text('changed')
    rejected=rescue_daily(parent,tmp_path/'rescue-tampered',night='2024-11-14')
    assert not rejected['results'] and 'product changed' in rejected['errors'][0]['error']
