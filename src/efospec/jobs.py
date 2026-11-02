"""Transport-independent extraction sessions and cancellable subprocess jobs."""
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import zipfile
import numpy as np
from .recipes import sky_mask, validate_recipe
from .revisions import Exposure, reference_directory


def vector(values):
    return [float(v) if np.isfinite(v) else None for v in values]


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
        if recipe.get('schema_version') == 2:
            from .joint_revisions import validate_joint_recipe
            recipe = validate_joint_recipe(recipe,exposure.window,exposure.hashes)
        else:
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
