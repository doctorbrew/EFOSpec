"""Local extraction workbench: authenticated HTTP, diagnostics and cancellable workers."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlsplit
import webbrowser

import numpy as np
from astropy.io import fits
from PIL import Image



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


from .jobs import Workbench


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
