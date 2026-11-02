"""End-to-end archive-bridge gates, including real reference fits and sky offsets."""
import json
from pathlib import Path
import shutil

import numpy as np
import pytest
from astropy.io import fits

from efospec.archive_calibration import fit_arc, arc_records
from efospec.inventory import inspect_file, sha256
from efospec.naming import science_stem
from efospec.rapid import select_archive, target_hint, reduce_night
from test_pypeit_adapter import write_raw

REFERENCE=Path(__file__).resolve().parents[1]/'trunk/src/ntt'


@pytest.mark.parametrize('grism', ['Gr11','Gr13'])
def test_archived_arc_fit_is_monotonic_with_whole_lines_held_out(grism):
    arc=next((REFERENCE/'archive/efosc/arc'/grism/'Free/slit1.0').glob('*.fits'))
    wave,qa=fit_arc(arc)
    assert np.all(np.diff(wave,axis=0)>0)
    assert qa['rms_angstrom']<1.5 and qa['held_out_rms_angstrom']<2.
    assert len(qa['held_out_lines'])>=2
    assert set(qa['held_out_lines'])<set(qa['reference_lines'])
    assert qa['arc_sha256']==sha256(arc)
    assert wave.shape==fits.getdata(arc).shape


def test_short_or_malformed_archive_identifications_fail(tmp_path):
    ids=tmp_path/'ids';ids.write_text('begin unmatched\nfeatures 0\n')
    with pytest.raises(ValueError,match='insufficient'):arc_records(ids)


def test_target_association_prefers_historical_geometry_and_converts_one_based(tmp_path):
    raw=write_raw(tmp_path,'raw.fits');frame=inspect_file(raw)
    assert target_hint(frame,tmp_path)[0]==449.
    h,s=frame['metadata'],frame['setup']
    stem=science_stem(h['OBJECT'],h['DATE-OBS'],s['grism'],s['filter'],s['slit'])
    extracted=tmp_path/(stem+'_1_ex.fits')
    fits.PrimaryHDU(np.ones(10),fits.Header({'DATE-OBS':h['DATE-OBS'],'APNUM1':'1 1 440 460'})).writeto(extracted)
    hint,record=target_hint(frame,tmp_path)
    assert hint==449. and record['association']=='historical_aperture'
    aperture=tmp_path/('ap'+stem+'_1');aperture.write_text('begin aperture\n    center 275.8438 500\n')
    hint,record=target_hint(frame,tmp_path)
    assert hint==pytest.approx(274.8438) and record['sha256']==sha256(aperture)


def test_reference_association_rejects_unsupported_geometry_missing_and_tied_sensitivity(tmp_path):
    raw=write_raw(tmp_path,'raw.fits');frame=inspect_file(raw)
    arc,sens=select_archive(frame,REFERENCE)
    assert arc.is_file() and sens.is_file()
    frame['setup']['binx']=1
    with pytest.raises(ValueError,match='2x2'):select_archive(frame,REFERENCE)
    frame['setup']['binx']=2
    with pytest.raises(ValueError,match='exactly one'):select_archive(frame,tmp_path)
    root=tmp_path/'archive/efosc'
    dest=root/'arc/Gr13/Free/slit1.0';dest.mkdir(parents=True);shutil.copyfile(arc,dest/arc.name)
    with pytest.raises(ValueError,match='missing or tied'):select_archive(frame,tmp_path)
    dest=root/'sens/Gr13/Free';dest.mkdir(parents=True)
    for name in ['a.fits','b.fits']:shutil.copyfile(sens,dest/name)
    with pytest.raises(ValueError,match='missing or tied'):select_archive(frame,tmp_path)


def test_reduce_night_recovers_injected_sky_shift_and_preserves_inputs(tmp_path):
    inputs=tmp_path/'raw';inputs.mkdir()
    raw=write_raw(inputs,'science.fits')
    frame=inspect_file(raw);arc,_=select_archive(frame,REFERENCE);wave,_=fit_arc(arc)
    y,x=np.indices(wave.shape)
    sky=np.full(wave.shape,100.)
    shift=12.
    for rest,amplitude in [(5577.338,500.),(6300.304,400.),(6363.776,150.)]:
        sky+=amplitude*np.exp(-.5*((wave-(rest-shift))/7.)**2)
    signal=8000.*np.exp(-.5*((x-449.)/1.7)**2)/(np.sqrt(2*np.pi)*1.7)
    rng=np.random.default_rng(127)
    electrons=rng.poisson(sky+signal)+rng.normal(0,7.8,wave.shape)
    with fits.open(raw,mode='update') as hdus:
        full=hdus[0].data.astype(float);full[:1015,99:950]=electrons/.91;hdus[0].data=full
    digest=sha256(raw)
    # A second frame fails association without erasing the successful exposure.
    write_raw(inputs,'missing-slit.fits',**{'OBJECT':'bad-slit','ESO INS SLIT1 NAME':'slit9.9'})
    write_raw(inputs,'unsupported.fits',**{'OBJECT':'unsupported','ESO INS GRIS1 NAME':'Gr7'})
    output=tmp_path/'reduced'
    result=reduce_night(inputs,output,REFERENCE,skip_report=True)
    assert len(result['results'])==1 and len(result['errors'])==1 and len(result['skipped'])==1
    science=result['results'][0]
    assert science['sky_flexure']['shift_angstrom']==pytest.approx(shift,abs=.15)
    assert science['sky_flexure']['held_out_6363_pass']
    assert science['raw_unchanged'] and sha256(raw)==digest
    assert len(result['source_sha256'])>=15
    assert json.loads((output/'run.json').read_text())['errors']==result['errors']
    with pytest.raises(FileExistsError):reduce_night(inputs,output,REFERENCE,skip_report=True)
    with pytest.raises(ValueError,match='no matching'):
        reduce_night(inputs,tmp_path/'empty',REFERENCE,targets=['absent'],skip_report=True)


def test_unsupported_only_run_is_incomplete_and_cli_returns_nonzero(tmp_path):
    from efospec.__main__ import main
    inputs = tmp_path/'raw'; inputs.mkdir()
    write_raw(inputs, 'filtered.fits', **{'ESO INS FILT1 NAME':'GG495'})
    write_raw(inputs, 'red.fits', **{'ESO INS GRIS1 NAME':'Gr16'})
    output = tmp_path/'reduced'
    code = main(['reduce-rapid', str(inputs), '--output', str(output),
                 '--reference-root', str(REFERENCE), '--skip-report'])
    assert code == 1
    run = json.loads((output/'run.json').read_text())
    assert run['execution_status'] == 'failed'
    assert len(run['skipped']) == 2 and not run['errors'] and not run['results']
    assert all(e['code'] == 'unsupported_setup' and e['action'] for e in run['skipped'])


def test_sky_failure_manifest_has_action_measurements_and_traceback(tmp_path):
    inputs = tmp_path/'raw'; inputs.mkdir()
    write_raw(inputs, 'blank.fits')
    output = tmp_path/'reduced'
    run = reduce_night(inputs, output, REFERENCE, skip_report=True)
    assert run['execution_status'] == 'failed'
    error = run['errors'][0]
    assert error['code'] == 'sky_flexure_unreliable' and error['stage'] == 'sky_flexure'
    assert error['action'] and 'lines' in error['diagnostics']
    assert 'SkyFlexureError' in Path(error['traceback']).read_text()
    assert not (output/'run.json.tmp').exists()
