"""Local extraction workbench: authenticated HTTP, diagnostics and cancellable workers."""
import base64
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser
import zipfile

import numpy as np
from astropy.io import fits
from PIL import Image

from .recipes import sky_mask, validate_recipe
from .revisions import Exposure, reference_directory


def vector(values):
    return [float(v) if np.isfinite(v) else None for v in values]


def diagnostics(exposure):
    """Display native pixels and calibrated arrays; no scientific work in JavaScript."""
    saved = exposure.images
    residual = saved['data']-saved['sky']
    onslit = saved.get('onslit',np.ones(residual.shape,dtype=bool)).astype(bool).copy()
    onslit[:,[0,-1]] = False
    finite = residual[np.isfinite(residual)&onslit]
    low, high = np.percentile(finite, [5,99.5])
    stretched = np.arcsinh(np.clip((residual-low)/max(high-low,1e-10),0,1)*8)/np.arcsinh(8)
    raster = np.flipud((255*np.where(onslit,np.nan_to_num(stretched),0)).astype(np.uint8).T)
    image = io.BytesIO()
    Image.fromarray(raster).save(image,format='PNG')
    wave = saved['waveair']
    edges = np.linspace(np.nanmin(wave), np.nanmax(wave),4)
    profiles = []
    for i, (lo, hi) in enumerate(zip(edges[:-1],edges[1:])):
        selected = (wave>=lo)&((wave<=hi) if i==2 else (wave<hi))&np.isfinite(residual)&onslit
        summed = np.where(selected,residual,0).sum(axis=0)
        summed[~selected.any(axis=0)] = np.nan
        profiles.append({'range':[float(lo),float(hi)],
            'spatial':vector(np.arange(residual.shape[1])+exposure.window.origin[1]),
            'flux':vector(summed)})
    with fits.open(exposure.result['product']) as hdus:
        values, h = hdus[0].data[:,0,:], hdus[0].header
        wavelength = h['CRVAL1']+(np.arange(values.shape[1])+1-h['CRPIX1'])*h['CD1_1']
        valid = hdus['VALID'].data.astype(bool)
        values = np.where(valid,values,np.nan)
    return {'object':exposure.result['object'], 'grism':exposure.result['grism'],
        'exptime':exposure.result['exptime_s'], 'snr':exposure.result['median_native_snr_4000_8500'],
        'window':{'shape':list(exposure.window.shape),'origin':list(exposure.window.origin)},
        'image':'data:image/png;base64,'+base64.b64encode(image.getvalue()).decode(),
        'trace':vector(saved['trace']+exposure.window.origin[1]),
        'sky_fraction':vector(np.mean(saved.get('sky_input_mask',np.zeros(residual.shape)),axis=0)),
        'profiles':profiles, 'primary':exposure.primary_object(), 'recipe':exposure.default_recipe(),
        'spectrum':dict(wave=vector(wavelength), optimal=vector(values[0]),
                        boxcar=vector(values[1]), sigma=vector(values[3]))}


class Workbench:
    def __init__(self, run, reference_root=None):
        # PypeIt installs a SIGINT handler on first import; initialise it on the
        # main thread and preserve the workbench's normal Ctrl-C behaviour.
        previous_handler = signal.getsignal(signal.SIGINT)
        import pypeit
        signal.signal(signal.SIGINT, previous_handler)
        self.run = Path(run).resolve()
        self.reference = Path(reference_root or reference_directory()).resolve()
        manifest = json.loads((self.run/'run.json').read_text())
        self.exposures = [{'id':Path(r['product']).name,'object':r['object'],
                           'grism':r['grism'],'exptime':r['exptime_s']} for r in manifest['results']]
        if not self.exposures:
            raise ValueError('the workbench needs a completed exposure')
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.job = self.process = self.log = None

    def exposure(self, product, job=None):
        run = self.run if job is None else self.job_directory(job)/'result'
        return Exposure(run,product,self.reference)

    def job_directory(self, identity):
        if not re.fullmatch(r'[0-9]{8}T[0-9]{6}-[0-9a-f]{12}', identity):
            raise ValueError('invalid revision ID')
        path = self.run/'revisions'/identity
        if not path.is_dir() or path.is_symlink():
            raise ValueError('unknown revision')
        return path

    def validate(self, product, recipe):
        exposure = self.exposure(product)
        recipe = validate_recipe(recipe,exposure.window,exposure.hashes)
        mask = sky_mask(recipe,exposure.window)
        return {'recipe':recipe,'sky_fraction':None if mask is None else vector(mask.mean(axis=0))}

    def history(self):
        records = []
        for path in sorted((self.run/'revisions').glob('*/job.json')):
            try:
                record = json.loads(path.read_text())
                if record['status'] == 'complete' and self.job_directory(record['id']) == path.parent:
                    records.append(record)
            except (ValueError, KeyError, OSError):
                continue
        return records

    def worker_command(self, product, recipe_file, output):
        return [sys.executable,'-m','efospec','reextract',str(self.run),'--product',product,
                '--recipe',str(recipe_file),'--output',str(output),'--reference-root',str(self.reference)]

    def _persist(self):
        directory = self.job_directory(self.job['id'])
        temporary = directory/'job.tmp'
        temporary.write_text(json.dumps(self.job,indent=2)+'\n')
        temporary.replace(directory/'job.json')

    def job_status(self):
        with self.lock:
            if self.job is None:
                return None
            if self.job['status']=='running' and self.process.poll() is not None:
                self.log.close()
                self.job['status'] = 'complete' if self.process.returncode==0 else 'failed'
                self.job['exit_code'] = self.process.returncode
                output = self.job_directory(self.job['id'])/'result'
                if (output/'run.json').is_file():
                    manifest = json.loads((output/'run.json').read_text())
                    self.job['products'] = [Path(r['product']).name for r in manifest['results']]
                    self.job['report'] = manifest.get('report')
                self._persist()
            record = dict(self.job)
            log = self.job_directory(self.job['id'])/'worker.log'
            with log.open('rb') as stream:
                stream.seek(max(0,log.stat().st_size-5000))
                record['log'] = re.sub(r'\x1b\[[0-9;]*m','',stream.read().decode(errors='replace'))
            return record

    def start(self, product, recipe):
        with self.lock:
            if self.job_status() and self.job['status']=='running':
                raise ValueError('an extraction is already running')
            recipe = self.validate(product,recipe)['recipe']
            identity = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+secrets.token_hex(6)
            directory = self.run/'revisions'/identity
            directory.mkdir(parents=True)
            request = directory/'request.json'
            request.write_text(json.dumps(recipe,indent=2)+'\n')
            self.log = (directory/'worker.log').open('wb')
            self.job = {'id':identity,'product':product,'status':'running','products':[],
                        'directory':str(directory/'result')}
            env = dict(os.environ, MPLBACKEND='Agg',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
            try:
                self.process = subprocess.Popen(self.worker_command(product,request,directory/'result'),
                    stdout=self.log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
            except OSError:
                self.log.close()
                self.job['status']='failed'
                self._persist()
                raise
            self._persist()
            return self.job_status()

    def cancel(self):
        with self.lock:
            self.job_status()
            if self.job and self.job['status']=='running':
                # Terminate the worker and any report-rendering child together.
                try:
                    os.killpg(self.process.pid,signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid,signal.SIGKILL)
                    self.process.wait(timeout=3)
                self.log.close()
                self.job['status']='cancelled'
                self._persist()
            return self.job_status()

    def close(self):
        self.cancel()

    def file(self, job, relative):
        root = (self.job_directory(job)/'result').resolve()
        path = (root/relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.suffix not in {'.fits','.asci','.json','.pdf','.jpg'}:
            raise ValueError('unknown revision product')
        return path

    def report_zip(self, job):
        root = self.job_directory(job)/'result'
        if not (root/'index.html').is_file():
            raise ValueError('report has not been generated')
        result = io.BytesIO()
        with zipfile.ZipFile(result,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob('*')):
                if (path.is_file() and not path.is_symlink() and path.suffix in
                        {'.html','.json','.jpg','.pdf','.fits','.asci'} and path.resolve().is_relative_to(root.resolve())):
                    archive.write(path,path.relative_to(root))
        return result.getvalue()


def create_server(app, port=0):
    assets = Path(__file__).with_name('web')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Local capabilities and file names must not enter HTTP access logs.

        def send(self, data, mime='application/json', status=200):
            if mime == 'application/json':
                data = json.dumps(data,allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def handle_request(self, post=False):
            try:
                origin = f'http://127.0.0.1:{self.server.server_port}'
                if self.headers.get('Host') != origin.removeprefix('http://') or self.headers.get('Origin',origin) != origin:
                    return self.send({'error':'local access required'},status=403)
                url = urlsplit(self.path)
                if not post and url.path in ('/','/app.js','/style.css'):
                    path = assets/({'/':'index.html'}.get(url.path,url.path[1:]))
                    return self.send(path.read_bytes(),mimetypes.guess_type(path)[0])
                if not secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+app.token):
                    return self.send({'error':'open the launch URL printed by efospec gui'},status=403)
                args = {k:v[0] for k,v in parse_qs(url.query).items()}
                if post:
                    length = int(self.headers.get('Content-Length','0'))
                    if not 0 < length <= 65536:
                        raise ValueError('request must contain at most 64 KiB of JSON')
                    body = json.loads(self.rfile.read(length))
                    if url.path == '/api/validate':
                        return self.send(app.validate(body['product'],body['recipe']))
                    if url.path == '/api/jobs':
                        return self.send(app.start(body['product'],body['recipe']))
                    if url.path == '/api/cancel':
                        return self.send(app.cancel())
                else:
                    if url.path == '/api/session':
                        return self.send({'exposures':app.exposures,'run':str(app.run),'revisions':app.history()})
                    if url.path == '/api/exposure':
                        return self.send(diagnostics(app.exposure(args['id'],args.get('job'))))
                    if url.path == '/api/jobs':
                        return self.send(app.job_status())
                    if url.path == '/api/file':
                        path = app.file(args['job'],args['path'])
                        return self.send(path.read_bytes(),'application/octet-stream')
                    if url.path == '/api/report':
                        return self.send(app.report_zip(args['job']),'application/zip')
                return self.send({'error':'unknown endpoint'},status=404)
            except (ValueError,KeyError,TypeError,OSError) as exc:
                return self.send({'error':str(exc)},status=400)

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request(post=True)
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve(run, reference_root=None, port=0, open_browser=True):
    app = Workbench(run,reference_root)
    server = create_server(app,port)
    url = f'http://127.0.0.1:{server.server_port}/#{app.token}'
    print(f'EFOSpec workbench: {url}',flush=True)
    print('Local session only. Ctrl-C stops the server and cancels active extraction.',flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
        server.server_close()
    return 0
