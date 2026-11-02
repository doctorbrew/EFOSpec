"""Read-only image packets and unverified candidate trials for failed exposures."""
from contextlib import redirect_stderr, redirect_stdout
from html import escape
import json
import os
from pathlib import Path
import traceback
from urllib.parse import quote

import numpy as np
from astropy.io import fits
from astropy.visualization import AsinhStretch, ImageNormalize
from astropy.wcs import WCS

from .inventory import sha256
from .native_calibration import save_json
from .recipes import validate_recipe
from .revisions import FailedExposure, prepare_recovery, reextract

from .figure_style import house_style


def _image(ax, data, extent=None):
    # Overscan/vignetted borders must not set the stretch for a faint field.
    dy,dx=[max(1,int(.03*n)) for n in data.shape]
    core=data[dy:-dy,dx:-dx]
    good = core[np.isfinite(core)]
    if not good.size:good=data[np.isfinite(data)]
    low, high = np.percentile(good, [.5, 99.5])
    high = max(high, low+1.)
    return ax.imshow(data, origin='lower', cmap='gray_r', aspect='auto', extent=extent,
                     norm=ImageNormalize(vmin=low, vmax=high, stretch=AsinhStretch(.08)))


def _traces(exposure):
    """Bind candidate IDs to the saved trace arrays, never to display ordering."""
    names = list(exposure.images['found_names'])
    return [exposure.images['found_traces'][names.index(c['name'])]+exposure.window.origin[1]
            for c in exposure.candidates]


@house_style
def plot_exposure(exposure, output):
    from .figure_style import COLORS, save_qc
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    raw = Path(exposure.frame['path'])
    full = fits.getdata(raw).astype(float)
    data = exposure.images['data']
    y0, x0 = exposure.window.origin
    ny, nx = data.shape
    extent = [x0-.5, x0+nx-.5, y0-.5, y0+ny-.5]
    rows = np.arange(ny)+y0
    traces = _traces(exposure)
    title = f"{exposure.result['object']} — identity UNVERIFIED\n{raw.name}"
    fig, axes = plt.subplots(1, 2, figsize=(20, 12), constrained_layout=True)
    im = _image(axes[0], full)
    axes[0].add_patch(Rectangle((x0-.5,y0-.5),nx,ny,fill=False,color=COLORS[1],lw=1.5))
    axes[0].set_title('Raw detector (ADU); rectangle = saved extraction window')
    fig.colorbar(im,ax=axes[0],label='ADU',shrink=.65)
    _image(axes[1], data, extent)
    axes[1].set_title('Window (electrons); saved candidate traces')
    for i, trace in enumerate(traces):
        axes[1].plot(trace, rows, color=COLORS[i%3], lw=1.2, label=f'C{i+1}')
    axes[1].legend()
    for ax in axes:
        ax.set_xlabel('Raw x / spatial pixel (zero based)')
        ax.set_ylabel('Raw y / spectral pixel (zero based)')
    fig.suptitle(title);save_qc(fig,output,'science',exposure.result['object']);plt.close(fig)

    residual = data-exposure.images['sky']
    fig = plt.figure(figsize=(20,16),constrained_layout=True)
    grid = fig.add_gridspec(2,2,height_ratios=[3,1.3])
    left, right, profile = fig.add_subplot(grid[0,0]), fig.add_subplot(grid[0,1]), fig.add_subplot(grid[1,:])
    for ax in [left,right]:
        _image(ax,residual,extent)
        ax.set_xlabel('Raw x (zero based)');ax.set_ylabel('Raw y (zero based)')
    left.set_title('Sky-subtracted window; no overlays')
    right.set_title('Same residual + saved traces; not a deblended image')
    for i,trace in enumerate(traces):
        right.plot(trace,rows,color=COLORS[i%3],lw=1.2,label=f'C{i+1}')
        profile.axvline(trace[ny//2],color=COLORS[i%3],lw=1.1,
                       label=f'C{i+1}: x={trace[ny//2]:.2f} at y={y0+ny//2}')
    right.legend()
    x = np.arange(nx)+x0
    for indices, style, label in [(np.arange(ny),'k-','All rows'),
            (np.arange(ny//4,ny//2),'--','Rows in second quarter'),
            (np.arange(ny//2,3*ny//4),':','Rows in third quarter')]:
        profile.plot(x,np.nanmedian(residual[indices],axis=0),style,lw=1.,label=label)
    # Edge pixels can dominate this diagnostic without representing a source.
    limits=np.percentile(residual[:,3:-3].mean(axis=0),[2,98])
    spread=max(limits[1]-limits[0],1.)
    profile.set_ylim(limits[0]-.2*spread,limits[1]+.35*spread)
    profile.set_xlabel('Raw spatial pixel x (zero based)')
    profile.set_ylabel('Median sky-subtracted electrons')
    profile.legend(ncol=3);profile.grid(False)
    fig.suptitle(title);save_qc(fig,output,'traces',exposure.result['object']);plt.close(fig)


@house_style
def acquisition_images(exposure, output):
    """Show same-OB acquisition frames without pretending they are registered."""
    from .figure_style import COLORS, save_qc
    import matplotlib.pyplot as plt
    raw = Path(exposure.frame['path'])
    header = fits.getheader(raw)
    records = []
    if header.get('ESO OBS ID') is None:
        return records
    for path in sorted(raw.parent.glob('*.fits')):
        h = fits.getheader(path)
        if (h.get('ESO OBS ID') != header['ESO OBS ID']
                or h.get('ESO TPL ID') != 'EFOSC_img_acq_MoveToSlit'
                or h.get('NAXIS') != 2):
            continue
        data = fits.getdata(path).astype(float)
        ny,nx=data.shape
        fig,axes=plt.subplots(1,2,figsize=(20,11),constrained_layout=True)
        _image(axes[0],data);axes[0].set_title('Full acquisition detector')
        half=min(180,ny//2,nx//2);y0=ny//2-half;x0=nx//2-half
        _image(axes[1],data[y0:y0+2*half,x0:x0+2*half],
               [x0-.5,x0+2*half-.5,y0-.5,y0+2*half-.5])
        axes[1].set_title('Detector-centre zoom; NOT a target identification')
        for ax in axes:
            ax.set_xlabel('Acquisition raw x (zero based)');ax.set_ylabel('Acquisition raw y (zero based)')
        celestial=bool(WCS(h).has_celestial)
        fig.suptitle(f"{path.name}\nFilter={h.get('ESO INS FILT1 NAME','?')}; slit={h.get('ESO INS SLIT1 NAME','?')}; "
                     f"EXPTIME={h.get('EXPTIME','?')} s\nNo registration to spectral detector; celestial WCS present={celestial}",fontsize=11)
        filename=f'acquisition-{len(records)+1}.png'
        save_qc(fig,output,Path(filename).stem,exposure.result['object']);plt.close(fig)
        records.append({'path':str(path),'sha256':sha256(path),'image':filename,
                        'has_celestial_wcs':celestial,'date_obs':h.get('DATE-OBS')})
    return records


def inspect_trial(exposure, recipe, result, seed_trace):
    from pypeit.specobjs import SpecObjs
    spec=SpecObjs.from_fitsfile(result['native_spec1d'])[0]
    trace=spec.TRACE_SPAT+exposure.window.origin[1]
    obj=recipe['objects'][0];row=int(obj['spec']-exposure.window.origin[0])
    valid=np.asarray(spec.OPT_MASK,dtype=bool)&(spec.OPT_COUNTS_IVAR>0)
    valid &= np.isfinite(spec.OPT_COUNTS)&np.isfinite(spec.OPT_COUNTS_IVAR)
    if not valid.any():raise ValueError('trial produced no finite optimally extracted samples with positive inverse variance')
    with fits.open(result['product']) as hdus:
        mask=hdus['VALID'].data.astype(bool)
        if not mask[0].any() or not np.isfinite(hdus[0].data[:,0,:][mask]).all():
            raise ValueError('trial exported no valid spectrum or non-finite valid samples')
    drift=float(trace[row]-obj['spat'])
    return {'execution':'passed','identity':'UNVERIFIED','product':result['product'],
        'native_spec1d':result['native_spec1d'],'anchor_drift_pixel':drift,
        'median_trace_departure_pixel':float(np.median(trace-seed_trace)),
        'trace_review_required':abs(drift)>obj['fwhm']/2,
        'valid_native_fraction':float(valid.mean()),'valid_flux_fraction':result['valid_flux_fraction']}


def trial_recipe(exposure, recipe, directory, seed_trace):
    with directory.with_suffix('.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
        try:
            run=reextract(exposure.run,Path(exposure.frame['path']).name,recipe,directory,
                          exposure.context.reference_root,failed=True,render_report=False)
            return inspect_trial(exposure,recipe,run['results'][0],seed_trace)
        except Exception as exc:
            traceback.print_exc()
            return {'execution':'failed','identity':'UNVERIFIED','error':str(exc),
                    'exception_type':type(exc).__name__,'log':str(directory.with_suffix('.log'))}


@house_style
def plot_trials(review, output):
    from .figure_style import COLORS, save_qc
    import matplotlib.pyplot as plt
    from pypeit.specobjs import SpecObjs
    passed=[c for c in review['candidates'] if c.get('trial',{}).get('execution')=='passed']
    if not passed:return
    fig,axes=plt.subplots(len(passed),1,figsize=(18,5*len(passed)),squeeze=False,constrained_layout=True)
    for ax,c in zip(axes[:,0],passed):
        s=SpecObjs.from_fitsfile(c['trial']['native_spec1d'])[0]
        good=s.OPT_MASK&(s.OPT_COUNTS_IVAR>0)&np.isfinite(s.OPT_COUNTS)
        ax.plot(s.OPT_WAVE,np.where(good,s.OPT_COUNTS,np.nan),color=COLORS[(c['number']-1)%3],lw=.65)
        ax.set_title(f"C{c['number']} — unverified candidate; anchor drift {c['trial']['anchor_drift_pixel']:+.2f} pixels",fontsize=10)
        ax.set_ylabel('Electrons / pixel');ax.axhline(0,color='gray',lw=.5)
        ax.set_xlabel('Vacuum wavelength (Å), archive-bridge calibration')
    fig.suptitle('Diagnostic candidate extractions — no target identity or flux validation')
    save_qc(fig,output,'trial-spectra',review['object']);plt.close(fig)


def write_review_html(review, output):
    def link(path,label):
        relative=os.path.relpath(path,output)
        return f'<a href="{quote(relative)}">{escape(label)}</a>'
    rows=[]
    for c in review['candidates']:
        t=c.get('trial',{});state=t.get('execution','not run')
        if t.get('trace_review_required'):state+='; trace drift needs review'
        drift=f"{t['anchor_drift_pixel']:+.2f}" if 'anchor_drift_pixel' in t else '—'
        rows.append(f"<tr><td>C{c['number']}</td><td>{c['anchor_raw_x']:.3f}</td><td>{c['anchor_raw_y']:.0f}</td>"
                    f"<td>{link(c['recipe'],'Recipe JSON')}</td><td>{state}</td><td>{drift}</td></tr>")
    images=['science.png','traces.png']+[a['image'] for a in review['acquisitions']]
    if (output/'trial-spectra.png').exists():images.append('trial-spectra.png')
    pictures=''.join(f'<p><a href="{quote(name)}"><img src="{quote(name)}" alt="{escape(name)}"></a></p>' for name in images)
    acquisitions=' · '.join(link(a['path'],Path(a['path']).name) for a in review['acquisitions']) or 'No matching acquisition frames found.'
    exports=' · '.join(link(p,p.name) for p in sorted(output.glob('FitQC_*')) if p.suffix in {'.pdf','.jpg'})
    background=''
    if (output/'C3-background-review.html').exists():
        background='<p>'+link(output/'C3-background-review.html','Provisional C3: polynomial background comparison and recipes')+'</p>'
    desktop_command=f'efospec background-gui "{output / "review.json"}"'
    text=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(review['object'])} — candidate QC</title><style>body{{font:16px system-ui;max-width:1100px;margin:30px auto;padding:0 18px;color:#172c43;background:#faf9f5}}h1{{font-size:24px}}p{{line-height:1.55}}a{{color:#1765a0}}img{{max-width:100%;height:auto}}table{{border-collapse:collapse;width:100%}}td,th{{padding:9px;border-bottom:1px solid #bbb;text-align:left}}.warning{{background:#fff0cb;padding:14px}}.scroll{{overflow-x:auto}}</style></head><body>
<h1>{escape(review['object'])}: candidate review</h1><p>{escape(review['raw_name'])}</p>
<p class="warning"><strong>Target identity UNVERIFIED.</strong> C1/C2/C3 are trace candidates, not identified supernovae. A passing trial only checks execution and finite output. It does not validate object identity, host deblending, sky regions or flux calibration.</p>
<p>All image axes and recipe coordinates use <strong>zero-based raw detector pixels</strong> (DS9 physical pixel coordinates are normally one greater). Images are not rotated or flipped. Saved trace curves, not nominal telescope pointing, define recipe anchors at the middle spectral row. Acquisition pixels are in their own detector images; no astrometric registration is asserted.</p>
<div class="scroll"><table><tr><th>Candidate</th><th>Anchor x</th><th>Anchor y</th><th>Recipe</th><th>Trial execution</th><th>Fitted x − seed x (px)</th></tr>{''.join(rows)}</table></div>
<p>Trial apertures use an initial FWHM of 4 pixels and boxcar half-width of 7 pixels; inspect these and the automatic sky regions before scientific use. Labels in trial FITS are neutral candidate names; ORIGOBJ retains the exposure label. Trials use the saved archive calibration, not the new native masters.</p>
<p>{link(review['raw_path'],'Raw spectral FITS')} · {link(output/'review.json','Full QC / input records JSON')} · {link(output/'target-selection.csv','Blank target-selection record')}</p>
<p>House-style PDF/JPG exports: {exports}</p>
<p>Neighbouring traces trigger aperture and background review. Open this packet in the native desktop editor with <code>{escape(desktop_command)}</code>. Select a candidate and two background bands; quadratic interpolation is the initial preview model.</p>{background}
<p>Associated acquisition FITS: {acquisitions}</p>{pictures}
<p>Identify a candidate or provide a raw (x,y) position with finding-chart/acquisition evidence. A candidate may be a field star, galaxy or spurious detection; choosing none is valid.</p></body></html>'''
    (output/'index.html').write_text(text)


def build_recovery_qc(run, raw_name, output, reference_root=None, *, test_recipes=False):
    """Create a fresh QC subfolder; never alter parent products or raw data."""
    exposure=FailedExposure(run,raw_name,reference_root)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    prepared=prepare_recovery(run,raw_name,output/'recipes',reference_root)
    review={'status':'running','identity':'UNVERIFIED','object':exposure.result['object'],
        'raw_name':raw_name,'raw_path':exposure.frame['path'],'parent_run':str(exposure.run),
        'input_sha256':dict(exposure.hashes),'coordinates':'raw_detector_pixels_zero_based',
        'candidates':[],'acquisitions':[]}
    save_json(output/'review.json',review)
    traces=_traces(exposure);middle=exposure.window.shape[0]//2
    for number,(candidate,trace) in enumerate(zip(prepared['candidates'],traces),1):
        path=Path(candidate['recipe']);recipe=json.loads(path.read_text())
        recipe['objects'][0].update(label=f'Candidate-{number}-UNVERIFIED',spat=float(trace[middle]))
        recipe=validate_recipe(recipe,exposure.window,exposure.hashes)
        save_json(path,recipe)
        review['candidates'].append({**candidate,'number':number,'anchor_raw_x':recipe['objects'][0]['spat'],
            'anchor_raw_y':recipe['objects'][0]['spec'],'recipe_sha256':sha256(path)})
    plot_exposure(exposure,output)
    review['acquisitions']=acquisition_images(exposure,output)
    if test_recipes:
        trials=output/'trials';trials.mkdir()
        for c,trace in zip(review['candidates'],traces):
            recipe=json.loads(Path(c['recipe']).read_text())
            c['trial']=trial_recipe(exposure,recipe,trials/f"candidate-{c['number']}",trace)
            save_json(output/'review.json',review)
        plot_trials(review,output)
    refreshed=FailedExposure(run,raw_name,reference_root)
    if refreshed.hashes!=exposure.hashes:raise ValueError('recovery inputs changed while creating QC')
    for a in review['acquisitions']:
        if sha256(Path(a['path']))!=a['sha256']:raise ValueError('acquisition input changed during QC')
    review.update(status='complete',raw_and_calibration_inputs_unchanged=True)
    review['qc_source_sha256']=sha256(Path(__file__))
    (output/'target-selection.csv').write_text('raw_file,verified_candidate,verified_raw_x_zero_based,verified_raw_y_zero_based,evidence,reviewer\n'+raw_name+',,,,,\n')
    save_json(output/'review.json',review);write_review_html(review,output)
    return review
