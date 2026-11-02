"""One observing date per invocation: inventory, reduction, QC and final report."""
import argparse
from collections import Counter
import csv
from datetime import date, datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from urllib.parse import quote
import uuid

from .inventory import inventory, sha256


def _save(path, value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    temporary.replace(path)


def _progress(night,output,message):
    line=f'[{night}] {message}'
    print(line,flush=True)
    with (output/'logs'/f'{night}-workflow.log').open('a') as log:
        log.write(datetime.now(timezone.utc).isoformat()+' '+line+'\n')


def _date(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        raise ValueError('observing date must be YYYY-MM-DD')
    date.fromisoformat(value)
    return value


def _invoke(arguments, output, log_name):
    """Capture the complete worker output; scientific failures do not stop reporting."""
    environment=os.environ.copy()
    environment.update(MPLBACKEND='Agg',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    source=str(Path(__file__).resolve().parents[1])
    environment['PYTHONPATH']=source+os.pathsep+environment.get('PYTHONPATH','')
    with (output/'logs'/log_name).open('w') as log:
        log.write(f"Observing night: {json.loads((output/'night.json').read_text())['night']}\n")
        log.write('Command: '+json.dumps([sys.executable,'-m','efospec',*arguments])+'\n');log.flush()
        return subprocess.run([sys.executable,'-m','efospec',*arguments],
                              stdout=log,stderr=subprocess.STDOUT,env=environment).returncode


def _log(state, output):
    report=inventory([state['input_dir']])
    path=output/'observing-log.json';_save(path,report)
    state['inventory_sha256']=sha256(path)
    columns=['requested_night','frame_night','utc_start','object','role','exposure_s',
             'grism','filter','slit','raw_file','sha256','issues']
    with (output/'observing-log.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(columns)
        for frame in report['frames']:
            h=frame['metadata'];setup=frame['setup']
            frame_night=datetime.strptime(frame['night'],'%Y%m%d').date().isoformat() if frame['night'] else ''
            writer.writerow([state['night'],frame_night,h['DATE-OBS'],h['OBJECT'],frame['role'],
                h['EXPTIME'],setup['grism'],setup['filter'],setup['slit'],frame['path'],
                frame['sha256'],'; '.join(frame['issues'])])
    selected=[f for f in report['frames'] if f['role'] in {'science','standard_candidate'} and 'duplicate_of' not in f]
    if report['errors'] or report['identity_conflicts']:
        raise ValueError('unreadable inputs or conflicting archive identities; inspect observing-log.json')
    foreign=[Path(f['path']).name for f in selected if f['night']!=state['night'].replace('-','')]
    if foreign:raise ValueError('science/standard exposures belong to another observing night: '+', '.join(foreign))
    if not selected or any(f['issues'] for f in selected):
        raise ValueError('no usable science/standard selection; inspect observing-log.json')
    state['selected_exposures']=len(selected)
    state['input_roles']=dict(Counter(f['role'] for f in report['frames'] if 'duplicate_of' not in f))
    return {'status':'complete','selected_exposures':len(selected)}


def _verify_inputs(state, output):
    path=output/'observing-log.json'
    if sha256(path)!=state['inventory_sha256']:raise ValueError('saved observing log changed')
    old=json.loads(path.read_text());current=inventory([state['input_dir']])
    if current['errors'] or current['identity_conflicts'] or (
        {f['path']:f['sha256'] for f in old['frames']}!={f['path']:f['sha256'] for f in current['frames']}):
        raise ValueError('raw inputs changed since the observing log; start a new dated revision')


def _reduce(state, output):
    if state['stages'].get('log',{}).get('status')!='complete':
        raise ValueError('complete the observing-log step before reduction')
    if (output/'reduction').exists():raise ValueError('reduction already attempted; start a new dated revision')
    _verify_inputs(state,output)
    code=_invoke(['reduce-rapid',state['input_dir'],'--output',str(output/'reduction'),
                  '--reference-root',state['reference_root'],'--include-standards','--skip-report'],
                 output,state['night']+'-reduction.log')
    manifest=output/'reduction/run.json'
    if not manifest.is_file():return {'status':'failed','worker_exit':code,'error':'worker produced no run manifest'}
    run=json.loads(manifest.read_text())
    if code not in (0,1) or run.get('execution_status')=='running':
        return {'status':'failed','worker_exit':code,'error':'reduction worker did not finish'}
    _verify_inputs(state,output)
    return {'status':'partial' if run['errors'] or run['skipped'] else 'complete','worker_exit':code,
            'spectra':len(run['results']),'failed':len(run['errors']),'unsupported':len(run['skipped'])}


def _report(state, output):
    run_dir=output/'reduction';manifest=run_dir/'run.json'
    if not manifest.is_file() or state['stages'].get('reduce',{}).get('status') not in {'complete','partial'}:
        return {'status':'failed','error':'no completed reduction; see the dated worker log'}
    _verify_inputs(state,output)
    args=['report',str(run_dir)]
    if state.get('plot_python'):args+=['--plot-python',state['plot_python']]
    code=_invoke(args,output,state['night']+'-report.log')
    report_path=run_dir/'report.json'
    rendered=json.loads(report_path.read_text()) if report_path.exists() else {}
    failures=[];packets=[]
    for failure in json.loads(manifest.read_text())['errors']:
        if failure.get('code')!='source_selection_required':continue
        raw=Path(failure['path']).name;packet=output/'QC'/Path(raw).stem
        if not packet.exists():
            qc_code=_invoke(['recovery-qc',str(run_dir),'--raw',raw,'--output',str(packet),
                '--reference-root',state['reference_root']],output,state['night']+'-QC-'+Path(raw).stem+'.log')
        else:qc_code=0
        review=packet/'review.json'
        q=json.loads(review.read_text()) if review.exists() else {}
        if qc_code or q.get('status')!='complete' or q.get('raw_name')!=raw or q.get('parent_run')!=str(run_dir):
            failures.append(raw)
        else:packets.append(str(packet/'index.html'))
    return {'status':'complete' if code==0 and rendered.get('status')=='complete' and not failures else 'partial',
            'worker_exit':code,'qc_packets':packets,'qc_failures':failures,'fieldnotes':str(run_dir/'index.html')}


def _index(state, output):
    """A dated entry point; the existing Fieldnotes page keeps its full plots."""
    links=[]
    for path,label in [(output/'observing-log.csv','Observing log (CSV)'),(output/'observing-log.json','Input provenance (JSON)'),
                       (output/'reduction/index.html','Spectra, traces and spatial profiles'),(output/'night.json','Workflow record')]:
        if path.is_file():links.append(f'<a href="{quote(str(path.relative_to(output)))}">{label}</a>')
    for path in sorted((output/'logs').glob('*.log')):
        links.append(f'<a href="logs/{quote(path.name)}">{escape(path.name)}</a>')
    qc=''.join(f'<li><a href="{quote(str(p.relative_to(output)))}">{escape(p.parent.name)}</a></li>' for p in sorted((output/'QC').glob('*/index.html')))
    rows=[];outcomes={}
    manifest=output/'reduction/run.json'
    if manifest.exists():
        run=json.loads(manifest.read_text())
        for group,label in [('results','Spectrum written'),('errors','Failed'),('skipped','Unsupported')]:
            for item in run[group]:outcomes[item.get('raw',item.get('path'))]=label+(': '+item['code'] if item.get('code') else '')
    log=output/'observing-log.json'
    if log.exists():
        for f in json.loads(log.read_text())['frames']:
            if f['role'] not in {'science','standard_candidate'} or 'duplicate_of' in f:continue
            h=f['metadata'];values=[h['OBJECT'],h['DATE-OBS'],f['role'],h['EXPTIME'],f['setup']['grism'],f['setup']['filter'],f['setup']['slit'],outcomes.get(f['path'],'Not reduced')]
            rows.append('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in values)+'</tr>')
    stages='; '.join(f"{name}: {value['status']}" for name,value in state['stages'].items())
    errors=''.join('<li>'+escape(v['error'])+'</li>' for v in state['stages'].values() if v.get('error'))
    page=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EFOSpec — {state['night']} nightly log</title><style>body{{font:16px system-ui;margin:28px;color:#172c43;background:#faf9f5}}p{{max-width:1100px;line-height:1.6}}td,th{{padding:9px;border-bottom:1px solid #ccc;text-align:left}}table{{border-collapse:collapse}}a{{color:#1765a0}}.scroll{{overflow-x:auto}}li{{margin:8px 0}}</style></head><body><h1>Observing night {state['night']}</h1><p>One epoch: noon UTC on {state['night']} to noon the following day. Processing revision: {escape(output.name)}.</p><p>{escape(stages)}</p><ul>{errors}</ul><div class="scroll"><table><tr><th>Object</th><th>UTC exposure start</th><th>Role</th><th>Seconds</th><th>Grism</th><th>Filter</th><th>Slit</th><th>Outcome</th></tr>{''.join(rows)}</table></div><p>Experimental archive-calibration reduction. Unsupported setups and failed checks remain explicit; this workflow does not enable native flux-calibrated extraction.</p><ul>{''.join('<li>'+link+'</li>' for link in links)}</ul><h2>{state['night']} — source-review QC</h2><ul>{qc or '<li>No candidate QC packets available.</li>'}</ul><p>Manual recipes remain exposure-specific; no C3 aperture or background bands are applied to a different exposure or date.</p></body></html>'''
    (output/'index.html').write_text(page)
    relative=quote(output.name+'/index.html')
    (output.parent/'index.html').write_text(f'<!doctype html><meta charset="utf-8"><title>{state["night"]} nightly log</title><meta http-equiv="refresh" content="0;url={relative}"><a href="{relative}">Observing night {state["night"]}</a>')
    from .epoch_report import build_epoch_page
    build_epoch_page(state['night'], output.parents[3])


def run_epoch(night, *, stage='all', project_root='.', plot_python=None):
    night=_date(night)
    if stage not in {'all','log','reduce','report'}:raise ValueError('unknown epoch stage')
    project=Path(project_root).resolve();input_dir=project/'data'/night
    if not input_dir.is_dir():raise ValueError(f'{night}: raw directory missing: {input_dir}')
    root=project/'runs'/night/'nightly';root.mkdir(parents=True,exist_ok=True)
    lock=root/'.running'
    try:handle=lock.open('x')
    except FileExistsError:raise ValueError(f'{night}: a nightly stage is already running; inspect {lock}') from None
    try:
        with handle:handle.write(f'{os.getpid()}\n')
        if stage in {'all','log'}:
            token=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
            output=root/token;output.mkdir();(output/'logs').mkdir()
            state={'schema_version':1,'night':night,'input_dir':str(input_dir),'output_dir':str(output),
                   'reference_root':str(Path(__file__).resolve().parents[2]/'trunk/src/ntt'),
                   'plot_python':plot_python,'stages':{},'status':'running'}
            _save(root/'current.json',{'night':night,'revision':token})
        else:
            pointer=json.loads((root/'current.json').read_text());output=(root/pointer['revision']).resolve()
            if pointer.get('night')!=night or output.parent!=root:raise ValueError('invalid dated revision pointer')
            state=json.loads((output/'night.json').read_text())
            if state['night']!=night or state['input_dir']!=str(input_dir):raise ValueError('revision belongs to a different date or input directory')
            if plot_python:state['plot_python']=plot_python
        steps=['log','reduce','report'] if stage=='all' else [stage]
        _save(output/'night.json',state)
        for step in steps:
            _progress(night,output,f'{step}: {output}')
            # Retain completed stages if a repeated or out-of-order invocation is rejected.
            if step=='reduce' and (output/'reduction').exists():raise ValueError('reduction already attempted; start with the log step for a new revision')
            state['stages'][step]={'status':'running'};_save(output/'night.json',state)
            try:state['stages'][step]={'log':_log,'reduce':_reduce,'report':_report}[step](state,output)
            except Exception as exc:
                state['stages'][step]={'status':'failed','error':str(exc)}
                (output/'logs'/f'{night}-{step}-error.log').write_text(traceback.format_exc())
                state['status']='failed';_save(output/'night.json',state);_index(state,output)
                raise
            statuses=[v['status'] for v in state['stages'].values()]
            state['status']='failed' if 'failed' in statuses else 'partial' if 'partial' in statuses else 'complete' if all(s in state['stages'] for s in ['log','reduce','report']) else 'prepared'
            _save(output/'night.json',state);_index(state,output)
        _progress(night,output,f'{state["status"]}: {output / "index.html"}')
        return state
    finally:lock.unlink()


def add_arguments(parser):
    parser.add_argument('night',help='One observing date, YYYY-MM-DD (noon UTC to following noon)')
    parser.add_argument('--project-root',default='.',help='Directory containing data/ and runs/')
    parser.add_argument('--plot-python',help='Python environment for house-style figures')


def exit_code(state):
    return 2 if state['status']=='failed' else 1 if state['status']=='partial' else 0


def script_main(stage):
    parser=argparse.ArgumentParser(description=f'EFOSpec dated epoch workflow: {stage}')
    add_arguments(parser);parser.set_defaults(project_root=str(Path(__file__).resolve().parents[2]))
    args=parser.parse_args()
    try:return exit_code(run_epoch(args.night,stage=stage,project_root=args.project_root,plot_python=args.plot_python))
    except (OSError,ValueError,ImportError) as exc:parser.exit(2,f'[{args.night}] {exc}\n')
