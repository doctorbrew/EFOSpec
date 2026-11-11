"""Exposure identity, unsupported products and immutable comparison publication."""
import json
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from efospec.iraf_comparison import discover, match_header, read_spectrum, compare_run, SETUP
from efospec.inventory import sha256


def header():
    h=fits.Header({'INSTRUME':'EFOSC','OBJECT':'SN2024test','DATE-OBS':'2024-11-15T01:00:00',
                   'EXPTIME':300.,'ARCFILE':'raw.fits','FILETYPE':22208,'PROCSOFT':'ntt_test',
                   'CTYPE1':'LINEAR','CRVAL1':4000.,'CRPIX1':2.,'CD1_1':2.,
                   'WAT1_001':'wtype=linear units=angstroms','BUNIT':'erg/cm2/s/Angstrom'})
    for k,v in zip(SETUP,('Gr13','Free','slit1.0',2,2,'fastL')):h[k]=v
    return h


def frame(h, path='raw.fits'):
    return dict(path=path,metadata=dict(h))


def write_product(path, h=None, native=False):
    hdus=[fits.PrimaryHDU(np.ones((4,1,40)),header=h or header())]
    if native:
        mask=np.ones((4,40),np.uint8);mask[:,10:14]=0
        hdus.append(fits.ImageHDU(mask,name='VALID'))
    fits.HDUList(hdus).writeto(path)
    return path


def test_identity_does_not_fall_back_to_object_name():
    h=header();f=frame(h)
    assert match_header(h,[f],'2024-11-14')[0]==f
    other=header();other['ARCFILE']='other.fits'
    with pytest.raises(ValueError,match='found 0'):match_header(other,[f],'2024-11-14')
    other=header();other['ESO INS SLIT1 NAME']='slit1.5'
    with pytest.raises(ValueError,match='found 0'):match_header(other,[f],'2024-11-14')
    with pytest.raises(ValueError,match='another observing night'):match_header(h,[f],'2024-11-13')


def test_ambiguous_metadata_and_combined_spectra_are_not_selected():
    h=header();del h['ARCFILE'];f=frame(h)
    assert match_header(h,[f],'2024-11-14')[1]=='unique_object_setup_time_exptime'
    with pytest.raises(ValueError,match='found 2'):match_header(h,[f,f],'2024-11-14')
    h['PROV1']='raw.fits';h['PROV2']='other.fits'
    with pytest.raises(ValueError,match='combined'):match_header(h,[f],'2024-11-14')


def test_discovery_is_header_based_and_deduplicates_bytes(tmp_path):
    p=write_product(tmp_path/'arbitrary.fits');(tmp_path/'copy.fits').write_bytes(p.read_bytes())
    h=header();h['PROCSOFT']='PypeIt 3.0.0';write_product(tmp_path/'native_f.fits',h)
    h=header();h['PYPEITV']='3.0.0';write_product(tmp_path/'native_version.fits',h)
    h=header();h['FILETYPE']=22107;write_product(tmp_path/'counts_f.fits',h)
    rows,errors=discover(tmp_path)
    assert not errors and len(rows)==1 and len(rows[0]['aliases'])==1


def test_reader_retains_flux_units_reference_pixel_and_native_mask(tmp_path):
    p=write_product(tmp_path/'s.fits',native=True)
    w,f,m=read_spectrum(p,native=True)
    assert w[0]==3998 and np.isnan(f[10:14]).all() and f[0]==1
    assert m['wavelength_medium']=='unspecified in IRAF header'
    assert m['aperture']=='unspecified'
    h=header();h['DC-FLAG']=1;write_product(tmp_path/'log.fits',h)
    with pytest.raises(ValueError,match='linear'):read_spectrum(tmp_path/'log.fits')
    h=header();h['BUNIT']='adu';write_product(tmp_path/'counts.fits',h)
    with pytest.raises(ValueError):read_spectrum(tmp_path/'counts.fits')


def test_no_native_delivery_remains_explicit_and_inputs_unchanged(tmp_path,monkeypatch):
    from efospec import inventory as module
    raw=tmp_path/'input';raw.mkdir();p=write_product(raw/'iraf.fits');before=sha256(p)
    f=frame(header(),str(raw/'raw.fits'));f.update(role='science',sha256='rawhash')
    monkeypatch.setattr(module,'inventory',lambda roots:dict(frames=[f],errors=[],identity_conflicts={}))
    run=tmp_path/'run';run.mkdir()
    manifest=run/'run.json';manifest.write_text(json.dumps(dict(night='2024-11-14',pypeit_version='3.0.0',
        execution_status='partial',results=[])))
    mh=sha256(manifest)
    r=compare_run(run,raw,tmp_path/'comparison')
    assert r['status']=='partial' and r['candidates'][0]['status']=='no_unique_native_product'
    assert sha256(p)==before and sha256(manifest)==mh


def test_report_rejects_changed_parent(tmp_path):
    from efospec.epoch_report import EpochPage
    from efospec.iraf_report import comparison_section
    revision=tmp_path/'revision';root=revision/'iraf-comparison';out=root/'a';out.mkdir(parents=True)
    (revision/'reduction').mkdir();(revision/'reduction/run.json').write_text('{}')
    p=out/'comparison.json';p.write_text(json.dumps(dict(parent_sha256='old')))
    (root/'current.json').write_text(json.dumps(dict(path='a',sha256=sha256(p))))
    assert 'earlier reduction' in comparison_section(EpochPage(tmp_path),revision)
