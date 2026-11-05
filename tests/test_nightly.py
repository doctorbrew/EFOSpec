"""Date isolation, immutable inputs and reporting after a partial reduction."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from efospec import nightly
from efospec.inventory import sha256
from test_pypeit_adapter import write_raw


@pytest.fixture
def epoch(tmp_path):
    raw=tmp_path/'data/2026-10-28';raw.mkdir(parents=True)
    file=write_raw(raw,'science.fits',**{'DATE-OBS':'2026-10-29T02:00:00','OBJECT':'SN<test>'})
    return tmp_path,file


def worker(monkeypatch, *, partial=False, crash=False, plot_failure=False):
    calls=[]
    def invoke(args,output,log_name):
        calls.append(args)
        (output/'logs'/log_name).write_text('fixture worker log')
        if args[0]=='reduce-rapid':
            if crash:return 2
            run=Path(args[args.index('--output')+1]);run.mkdir()
            raw=str(Path(args[1])/'science.fits')
            errors=[dict(path=raw,object='SN<test>',code='source_selection_required')] if partial else []
            result=[] if partial else [dict(raw=raw,object='SN<test>')]
            (run/'run.json').write_text(json.dumps(dict(execution_status='partial' if partial else 'complete',results=result,errors=errors,skipped=[])))
            return int(partial)
        if args[0]=='report':
            run=Path(args[1]);(run/'index.html').write_text('Fieldnotes')
            (run/'report.json').write_text(json.dumps({'status':'incomplete' if plot_failure else 'complete'}))
            return int(plot_failure)
        assert args[0]=='recovery-qc'
        out=Path(args[args.index('--output')+1]);out.mkdir(parents=True)
        (out/'review.json').write_text(json.dumps({'status':'complete','raw_name':'science.fits','parent_run':args[1]}))
        (out/'index.html').write_text('Candidate QC')
        return 0
    monkeypatch.setattr(nightly,'_invoke',invoke)
    return calls


def test_partial_reduction_still_presents_one_dated_report_and_qc(epoch,monkeypatch,capsys):
    root,raw=epoch;before=sha256(raw);calls=worker(monkeypatch,partial=True)
    state=nightly.run_epoch('2026-10-28',project_root=root)
    assert state['status']=='partial' and nightly.exit_code(state)==1
    assert state['stages']['report']['status']=='complete'
    assert [c[0] for c in calls]==['reduce-rapid','report','recovery-qc']
    output=Path(state['output_dir']);page=(output/'index.html').read_text()
    assert 'Observing night 2026-10-28' in page and 'SN&lt;test&gt;' in page
    assert 'source_selection_required' in page and 'QC/science/index.html' in page
    assert 'reduction/index.html' in page and 'observing-log.csv' in page
    assert '2026-10-28,2026-10-28,2026-10-29T02:00:00' in (output/'observing-log.csv').read_text()
    assert not (root/'runs/2026-10-29').exists()
    assert sha256(raw)==before
    assert not (output.parent/'.running').exists()
    daily_log=root/'runs/2026-10-28/index.html'
    assert state['daily_log']==str(daily_log)
    assert daily_log.is_file() and 'ePESSTO+' in daily_log.read_text()
    assert capsys.readouterr().out.splitlines()[-1].endswith(str(daily_log))
    assert json.loads((output/'night.json').read_text())['daily_log']==str(daily_log)


def test_separate_steps_preserve_products_and_new_log_starts_new_revision(epoch,monkeypatch):
    root,_=epoch;calls=worker(monkeypatch)
    first=nightly.run_epoch('2026-10-28',stage='log',project_root=root)
    assert first['status']=='prepared' and not calls
    reduced=nightly.run_epoch('2026-10-28',stage='reduce',project_root=root)
    assert reduced['output_dir']==first['output_dir']
    manifest=Path(first['output_dir'])/'reduction/run.json';before=sha256(manifest)
    with pytest.raises(ValueError,match='already attempted'):
        nightly.run_epoch('2026-10-28',stage='reduce',project_root=root)
    assert sha256(manifest)==before
    complete=nightly.run_epoch('2026-10-28',stage='report',project_root=root)
    assert nightly.exit_code(complete)==0
    second=nightly.run_epoch('2026-10-28',stage='log',project_root=root)
    assert first['output_dir']!=second['output_dir'] and sha256(manifest)==before


def test_target_scope_is_persisted_passed_to_worker_and_reported(epoch, monkeypatch):
    root, raw = epoch
    write_raw(raw.parent,'standard.fits', **{'DATE-OBS':'2026-10-29T03:00:00','OBJECT':'vma2','ESO DPR TYPE':'STD'})
    calls = worker(monkeypatch)
    state = nightly.run_epoch('2026-10-28', project_root=root, targets=['SN<test>'])
    assert state['selected_exposures'] == 1
    assert calls[0][-2:] == ['--target','SN<test>']
    html = (root/'runs/2026-10-28/index.html').read_text()
    assert 'Selected targets: SN&lt;test&gt;' in html and 'Outside selected targets' in html
    with pytest.raises(ValueError,match='target selection changed'):
        nightly.run_epoch('2026-10-28',stage='report',project_root=root,targets=['vma2'])


@pytest.mark.parametrize('change',['modify','add'])
def test_changed_or_added_raw_inputs_require_a_new_log(epoch,monkeypatch,change):
    root,raw=epoch;calls=worker(monkeypatch)
    state=nightly.run_epoch('2026-10-28',stage='log',project_root=root)
    if change=='modify':
        from astropy.io import fits
        with fits.open(raw,mode='update') as hdus:hdus[0].header['OBJECT']='different'
    else:write_raw(raw.parent,'added.fits',**{'DATE-OBS':'2026-10-29T03:00:00'})
    with pytest.raises(ValueError,match='raw inputs changed'):
        nightly.run_epoch('2026-10-28',stage='reduce',project_root=root)
    assert not calls
    saved=json.loads((Path(state['output_dir'])/'night.json').read_text())
    assert saved['status']=='failed' and (Path(state['output_dir'])/'index.html').exists()


def test_foreign_science_night_is_rejected_but_logged(epoch):
    root,raw=epoch
    write_raw(raw.parent,'other.fits',**{'DATE-OBS':'2026-10-30T03:00:00'})
    with pytest.raises(ValueError,match='another observing night'):
        nightly.run_epoch('2026-10-28',project_root=root)
    logs=list((root/'runs/2026-10-28/nightly').glob('*/observing-log.csv'))
    assert len(logs)==1 and 'other.fits' in logs[0].read_text()
    assert not (logs[0].parent/'reduction').exists()


@pytest.mark.parametrize('value',['2026-02-30','2026-1-2','../2026-10-28','2026-10-28,2026-10-29'])
def test_only_one_valid_date_is_accepted(tmp_path,value):
    with pytest.raises(ValueError):nightly.run_epoch(value,project_root=tmp_path)
    assert not (tmp_path/'runs').exists()


def test_crashed_worker_has_dated_failure_report_and_no_false_success(epoch,monkeypatch):
    root,_=epoch;calls=worker(monkeypatch,crash=True)
    state=nightly.run_epoch('2026-10-28',project_root=root)
    assert nightly.exit_code(state)==2
    assert state['stages']['report']['status']=='failed'
    assert [c[0] for c in calls]==['reduce-rapid']
    assert 'worker produced no run manifest' in (Path(state['output_dir'])/'index.html').read_text()


def test_report_failure_does_not_change_reduction_or_hide_results(epoch,monkeypatch):
    root,_=epoch;worker(monkeypatch,plot_failure=True)
    state=nightly.run_epoch('2026-10-28',project_root=root)
    assert state['status']=='partial' and state['stages']['reduce']['spectra']==1
    assert 'Spectrum written' in (Path(state['output_dir'])/'index.html').read_text()


def test_lock_and_revision_pointer_cannot_cross_dates(epoch):
    root,_=epoch;state=nightly.run_epoch('2026-10-28',stage='log',project_root=root)
    folder=Path(state['output_dir']).parent
    lock=folder/'.running';lock.write_text('123')
    with pytest.raises(ValueError,match='already running'):nightly.run_epoch('2026-10-28',stage='reduce',project_root=root)
    assert lock.read_text()=='123';lock.unlink()
    (folder/'current.json').write_text(json.dumps({'night':'2026-10-28','revision':'../../2026-10-29'}))
    with pytest.raises(ValueError,match='invalid dated'):nightly.run_epoch('2026-10-28',stage='reduce',project_root=root)


def test_worker_invocation_uses_current_python_and_a_dated_log(epoch,monkeypatch):
    root,_=epoch;state=nightly.run_epoch('2026-10-28',stage='log',project_root=root)
    output=Path(state['output_dir']);calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs));kwargs['stdout'].write('worker evidence\n')
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(nightly.subprocess,'run',run)
    assert nightly._invoke(['inventory',state['input_dir']],output,'2026-10-28-check.log')==1
    assert calls[0][0][:3]==[nightly.sys.executable,'-m','efospec']
    assert calls[0][1]['env']['MPLBACKEND']=='Agg'
    log=(output/'logs/2026-10-28-check.log').read_text()
    assert 'Observing night: 2026-10-28' in log and 'worker evidence' in log


def test_cli_date_selects_only_its_epoch_log(epoch):
    root,_=epoch
    from efospec.__main__ import main
    assert main(['night','2026-10-28','--stage','log','--project-root',str(root)])==0
    assert (root/'runs/2026-10-28/nightly/index.html').exists()


def test_selected_native_diagnostics_run_after_archive_without_changing_its_manifest(epoch,monkeypatch):
    root,raw=epoch
    calls=worker(monkeypatch)
    original=nightly._invoke
    def invoke(args,out,log):
        if args[0]!='validate-native':return original(args,out,log)
        calls.append(args)
        dest=Path(args[args.index('--output')+1]);dest.mkdir()
        (dest/'validation.json').write_text(json.dumps({'status':'incomplete',
            'results':[],'errors':[{'raw':str(raw),'error':'weak sky'}],'skipped':[]}))
        return 1
    monkeypatch.setattr(nightly,'_invoke',invoke)
    native=root/'native';native.mkdir()
    (native/'inputs.json').write_text(json.dumps({'frames':[{'path':str(raw),'sha256':sha256(raw)}]}))
    (native/'run.json').write_text(json.dumps({'groups':[{'associated_exposures':[str(raw)]}]}))
    state=nightly.run_epoch('2026-10-28',project_root=root,native_calibrations=native)
    assert [c[0] for c in calls]==['reduce-rapid','validate-native','report']
    assert state['stages']['native_checks']['status']=='partial'
    assert state['status']=='partial'
    assert 'Contemporary raw-calibration checks' in (root/'runs/2026-10-28/index.html').read_text()
    with pytest.raises(ValueError,match='selection changed'):
        nightly.run_epoch('2026-10-28',stage='report',project_root=root,native_calibrations=root/'other')


def test_native_selection_cannot_process_exposures_outside_requested_night(epoch,monkeypatch):
    root,raw=epoch;calls=worker(monkeypatch)
    native=root/'native';native.mkdir()
    (native/'inputs.json').write_text(json.dumps({'frames':[]}))
    (native/'run.json').write_text(json.dumps({'groups':[{'associated_exposures':['foreign.fits']}]}))
    with pytest.raises(ValueError,match='does not match'):
        nightly.run_epoch('2026-10-28',project_root=root,native_calibrations=native)
    assert not calls
