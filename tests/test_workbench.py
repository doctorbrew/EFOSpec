import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from test_revisions import saved_exposure


def test_diagnostics_use_native_detector_coordinates(saved_exposure):
    from efospec.workbench import diagnostics
    from efospec.revisions import Exposure
    run, reference, _ = saved_exposure
    data = diagnostics(Exposure(run,'test_f.fits',reference))
    assert data['window'] == {'shape':[160,141],'origin':[0,299]}
    assert data['image'].startswith('data:image/png;base64,')
    assert data['primary']['spat'] == pytest.approx(347.,abs=.3)
    assert len(data['profiles']) == 3
    assert all(p['flux'][0] is None and p['flux'][-1] is None for p in data['profiles'])
    assert data['profiles'][0]['spatial'][0] == 299
    assert len(data['spectrum']['optimal']) == len(data['spectrum']['wave'])
    json.dumps(data, allow_nan=False)


def test_http_access_validation_and_file_boundaries(saved_exposure):
    from efospec.workbench import Workbench, create_server
    run, reference, _ = saved_exposure
    app = Workbench(run, reference)
    server = create_server(app)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def get(path, token=True, origin=None, payload=None):
        headers = {'Authorization':'Bearer '+app.token} if token else {}
        if origin: headers['Origin'] = origin
        if payload is not None: headers['Content-Type']='application/json'
        request = Request(base+path,headers=headers,data=None if payload is None else json.dumps(payload).encode())
        return urlopen(request)
    try:
        assert b'EFOSpec' in get('/').read()
        with pytest.raises(HTTPError) as error:
            get('/api/session',token=False)
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            get('/api/session',origin='https://foreign.example')
        assert error.value.code == 403
        session = json.load(get('/api/session'))
        assert session['exposures'][0]['id'] == 'test_f.fits'
        data = json.load(get('/api/exposure?id=test_f.fits'))
        payload = {'product':'test_f.fits','recipe':data['recipe']}
        validated = json.load(get('/api/validate',payload=payload))
        assert validated['recipe'] == data['recipe']
        payload['recipe']['input_sha256']['raw'] = '0'*64
        with pytest.raises(HTTPError) as error:
            get('/api/jobs',payload=payload)
        assert error.value.code == 400
        assert app.job_status() is None
        for path in ('/api/exposure?id=unknown','/api/file?job=../&path=../../run.json','/missing'):
            with pytest.raises(HTTPError): get(path)
        assert not (run/'revisions').exists()
    finally:
        server.shutdown(); server.server_close(); app.close(); thread.join()


def test_job_cancellation_is_durable_and_preserves_parent(saved_exposure, monkeypatch):
    import sys
    from efospec.workbench import Workbench
    from efospec.inventory import sha256
    run, reference, _ = saved_exposure
    app = Workbench(run,reference)
    before = sha256(run/'products/test_f.fits')
    # Exercise the real process lifecycle with a predictable long-running worker.
    monkeypatch.setattr(app,'worker_command',lambda *args: [sys.executable,'-c','import time; time.sleep(120)'])
    try:
        recipe = app.exposure('test_f.fits').default_recipe()
        job = app.start('test_f.fits',recipe)
        assert job['status'] == 'running'
        with pytest.raises(ValueError, match='running'):
            app.start('test_f.fits',recipe)
        cancelled = app.cancel()
        assert cancelled['status'] == 'cancelled'
        assert app.job_status()['status'] == 'cancelled'
        assert json.loads((run/'revisions'/job['id']/'job.json').read_text())['status'] == 'cancelled'
        assert sha256(run/'products/test_f.fits') == before
    finally:
        app.close()


def test_cli_starts_in_fresh_process_before_http_threads_import_pypeit(saved_exposure,tmp_path):
    import signal
    import subprocess
    import sys
    from urllib.parse import urlsplit
    run,reference,_=saved_exposure
    with (tmp_path/'gui.log').open('w') as log:
        process=subprocess.Popen([sys.executable,'-m','efospec','browser-prototype',str(run),
            '--reference-root',str(reference),'--no-browser'],stdout=subprocess.PIPE,
            stderr=log,text=True)
        try:
            line=process.stdout.readline()
            assert line.startswith('EFOSpec workbench: ')
            url=urlsplit(line.split('workbench: ',1)[1].strip())
            request=Request(f'{url.scheme}://{url.netloc}/api/exposure?id=test_f.fits',
                            headers={'Authorization':'Bearer '+url.fragment})
            data=json.load(urlopen(request,timeout=15))
            assert data['window']['shape']==[160,141]
            process.send_signal(signal.SIGINT)
            assert process.wait(timeout=10)==0
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)


def test_report_download_keeps_relative_assets_and_excludes_external_links(saved_exposure,tmp_path):
    import io
    import zipfile
    from efospec.workbench import Workbench
    run,reference,_=saved_exposure
    app=Workbench(run,reference)
    identity='20260101T010203-abcdef123456'
    result=run/'revisions'/identity/'result';(result/'style-preview').mkdir(parents=True)
    (result/'index.html').write_text('<img src="style-preview/figure.jpg">')
    (result/'style-preview/figure.jpg').write_bytes(b'image')
    private=tmp_path/'unrelated.json';private.write_text('do not include')
    (result/'outside.json').symlink_to(private)
    record={'id':identity,'status':'complete','product':'test_f.fits','products':['test_f.fits']}
    (result.parent/'job.json').write_text(json.dumps(record))
    assert app.history()==[record]
    with zipfile.ZipFile(io.BytesIO(app.report_zip(identity))) as archive:
        assert set(archive.namelist())=={'index.html','style-preview/figure.jpg'}
    with pytest.raises(ValueError):app.file(identity,'../../../../unrelated.json')
    with pytest.raises(ValueError):app.file(identity,'outside.json')
    assert app.file(identity,'style-preview/figure.jpg').name=='figure.jpg'
