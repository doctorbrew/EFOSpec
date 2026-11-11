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
from astropy.wcs import WCS

from .inventory import sha256
from .native_calibration import save_json
from .recipes import validate_recipe
from .revisions import Exposure, FailedExposure, prepare_recovery, reextract

from .figure_style import house_style
from .profile_limits import _profile_limit_samples, _profile_limits
from .image_display import image_normalization, mark_zoom_region

from .trace_geometry import TRACE_STYLES, TRACE_LINEWIDTH

TRACE_COLORS = ('xkcd:red', 'xkcd:dodger blue', 'xkcd:green', 'xkcd:brown')

# The bounded background selection already treats these columns as off-slit.
SLIT_EDGE_MARGIN = 3



def _candidate_label(ax, x, label, color):
    """Label a candidate just beside its trace, inside the lower axis edge."""
    low, high = ax.get_xlim()
    offset = .012*(high-low)
    right_side = x+2*offset < high
    return ax.text(x+offset if right_side else x-offset, .03, label,
                   transform=ax.get_xaxis_transform(), rotation=90,
                   ha='left' if right_side else 'right', va='bottom', fontsize=21.6,
                   color=color, zorder=10, clip_on=True,
                   bbox={'boxstyle':'square,pad=0.3', 'facecolor':'white',
                         'edgecolor':color, 'linewidth':1.2, 'alpha':.7})



def _compact_counts(value, position=None):
    if value == 0:
        return '0'
    mantissa, exponent = f'{value:.2e}'.split('e')
    return f'{mantissa.rstrip("0").rstrip(".")}e{int(exponent)}'


def _image(ax, data, extent=None, *, residual=False, normalization=None, cmap='gray_r'):
    norm, metadata = normalization or image_normalization(data, residual=residual, cmap=cmap)
    image = ax.imshow(data, origin='lower', cmap=cmap, aspect='auto', extent=extent,
                      norm=norm, interpolation='nearest')
    image._efospec_display = metadata
    return image


def _traces(exposure):
    """Bind candidate IDs to the saved trace arrays, never to display ordering."""
    names = list(exposure.images['found_names'])
    return [exposure.images['found_traces'][names.index(c['name'])]+exposure.window.origin[1]
            for c in exposure.candidates]


@house_style
def plot_exposure(exposure, output):
    from .figure_style import save_qc
    import matplotlib.pyplot as plt
    raw = Path(exposure.frame['path'])
    full = fits.getdata(raw).astype(float)
    data = exposure.images['data']
    y0, x0 = exposure.window.origin
    ny, nx = data.shape
    extent = [x0-.5, x0+nx-.5, y0-.5, y0+ny-.5]
    rows = np.arange(ny)+y0
    traces = _traces(exposure)
    stage = str(exposure.images.get('sky_mask_stage', ''))
    sky_available = not stage.startswith('source_finding_only_no_')
    residual = data-exposure.images['sky'] if sky_available else data
    # Saved packets have no detection S/N. Rank display colors by median
    # signal sampled along each trace, while preserving the candidate IDs.
    strengths = [float(np.nanmedian([np.interp(t-x0, np.arange(nx), row)
                  for t, row in zip(trace, residual)])) for trace in traces]
    order = sorted(range(len(traces)), key=lambda i: (-strengths[i] if np.isfinite(strengths[i]) else np.inf, i))
    colors = {i: TRACE_COLORS[0] for i in range(len(traces))}
    finite_traces = np.concatenate([t[np.isfinite(t)] for t in traces]) if traces else np.array([])
    xlimits = (min(extent[0], finite_traces.min()-1) if finite_traces.size else extent[0],
               max(extent[1], finite_traces.max()+1) if finite_traces.size else extent[1])
    title = exposure.result['object']
    fig, axes = plt.subplots(1, 2, figsize=(20, 12), constrained_layout=True)
    im = _image(axes[0], full)
    axes[0].set_title('Raw detector')
    fig.colorbar(im,ax=axes[0],label='ADU',shrink=.65)
    window_image = _image(axes[1], data, extent)
    axes[1].set_title('Candidate traces')
    for i, trace in enumerate(traces):
        axes[1].plot(trace, rows, color=colors[i], ls=TRACE_STYLES[i%4], lw=TRACE_LINEWIDTH)
    axes[1].set_xlim(*xlimits)
    axes[1].set_ylim(extent[2], extent[3])
    zoom_bounds = mark_zoom_region(axes[0], axes[1])
    image_displays = {'raw_detector':im._efospec_display,
                      'processed_window':window_image._efospec_display,
                      'zoom_raw_bounds_xy':zoom_bounds}
    label_row = int(.03*(ny-1))
    for i, trace in enumerate(traces):
        _candidate_label(axes[1], trace[label_row], f'C{i+1}', colors[i])
    for ax in axes:
        ax.set_xlabel('Raw x / spatial pixel')
        ax.set_ylabel('Raw y / spectral pixel')
    fig.suptitle(title);save_qc(fig,output,'science',exposure.result['object'],tick_fontsize=24,title_fontsize=26,label_fontsize=28.6);plt.close(fig)

    # A zero placeholder from a failed selection is not a fitted sky model.
    fig, (left, right) = plt.subplots(1, 2, figsize=(20,12), constrained_layout=True)
    for ax in [left,right]:
        residual_image = _image(ax,residual,extent,residual=sky_available)
        ax.set_xlabel('Raw x / spatial pixel');ax.set_ylabel('Raw y / spectral pixel')
    left.set_title('Sky residual' if sky_available else 'Window (no sky fit)')
    right.set_title('Residual + traces' if sky_available else 'Traces (no sky fit)')
    for i, trace in enumerate(traces):
        right.plot(trace,rows,color=colors[i],ls=TRACE_STYLES[i%4],lw=TRACE_LINEWIDTH)
    # Keep both residual views on the same detector bounds, including traces
    # that extend beyond the saved window. No candidate is silently cropped.
    for ax in [left, right]:
        ax.set_xlim(*xlimits)
        ax.set_ylim(extent[2], extent[3])
    for i, trace in enumerate(traces):
        _candidate_label(right, trace[label_row], f'C{i+1}', colors[i])
    subtitle = '' if sky_available else '\nSky subtraction unavailable: no fitted background'
    fig.suptitle(title+subtitle)
    image_displays['residual'] = residual_image._efospec_display
    save_qc(fig,output,'traces',exposure.result['object'],tick_fontsize=24,title_fontsize=26,label_fontsize=28.6);plt.close(fig)

    # A separate wide figure remains legible when it spans the report grid.
    from .profile_background import load_profile_background, summed_profile
    background = load_profile_background(exposure, output)
    profile_sky_available = background is not None or sky_available
    profile_residual = background['residual'] if background else residual
    valid_rows = (background['valid_rows'] if background else
                  np.asarray(exposure.images.get('sky_valid_rows', np.ones(ny, dtype=bool))))
    supported_xlimits = background['x_limits'] if background else xlimits
    # Candidate positions remain visible even when the fitted background only
    # supports a smaller interval. Do not extrapolate its profile into that gap.
    anchors = [trace[ny//2] for trace in traces if np.isfinite(trace[ny//2])]
    profile_xlimits = (min([supported_xlimits[0]]+[x-3 for x in anchors]),
                       max([supported_xlimits[1]]+[x+3 for x in anchors]))
    fig, profile = plt.subplots(figsize=(20,8.5), constrained_layout=True)
    for i, trace in enumerate(traces):
        profile.axvline(trace[ny//2],color=colors[i],ls=TRACE_STYLES[i%4],lw=4.2)
    x = np.arange(nx)+x0
    protected = np.zeros(nx, dtype=bool)
    for trace in traces:
        finite = trace[np.isfinite(trace)]
        if finite.size:
            protected |= (x >= finite.min()-3) & (x <= finite.max()+3)
    limit_samples, exclusions, row_ranges = [], {}, {}
    for indices, style, label in [(np.arange(ny),'k-','All rows'),
            (np.arange(ny//4,ny//2),'--','Second quarter'),
            (np.arange(ny//2,3*ny//4),':','Third quarter')]:
        if profile_sky_available:
            values, row_count = summed_profile(profile_residual, indices, valid_rows,
                spatial_columns=((x >= supported_xlimits[0]) & (x <= supported_xlimits[1]))
                                if background else None)
        else:
            values, row_count = np.nanmedian(residual[indices],axis=0), len(indices)
        if background:
            values = np.where((x >= supported_xlimits[0]) & (x <= supported_xlimits[1]), values, np.nan)
        # Slit-boundary columns carry no fitted background and overwhelm the
        # sources by an order of magnitude; keep them plotted but out of scale.
        for_limits, excluded = _profile_limit_samples(values, protected,
                                                      edge_margin=SLIT_EDGE_MARGIN)
        for_limits[(x < profile_xlimits[0]) | (x > profile_xlimits[1])] = np.nan
        exclusions[label] = x[excluded].tolist()
        limit_samples.append(for_limits)
        first, last = int(y0+indices[0]), int(y0+indices[-1])
        row_ranges[label] = {'raw_y_first':first, 'raw_y_last':last,
                             'bounds':'inclusive', 'rows':len(indices), 'used_rows':row_count}
        short_label = {'All rows':'Full range', 'Second quarter':'Q2', 'Third quarter':'Q3'}[label]
        coverage = f' ({row_count}/{len(indices)} rows)' if row_count != len(indices) else ''
        profile.plot(x,values/1000.,style,lw=2.,label=f'{short_label}: y={first}--{last}'+coverage)
    # Keep every plotted sample, including spikes below the chosen viewport.
    limits = _profile_limits(limit_samples, background_subtracted=profile_sky_available)
    if limits is not None:
        limits = tuple(value/1000. for value in limits)
        profile.set_ylim(*limits)
    profile.set_xlim(*profile_xlimits)
    from matplotlib.ticker import ScalarFormatter
    formatter = ScalarFormatter(useOffset=False)
    formatter.set_scientific(False)
    profile.yaxis.set_major_formatter(formatter)
    for i, trace in enumerate(traces):
        _candidate_label(profile, trace[ny//2], f'C{i+1}', colors[i])
    profile.set_xlabel('Spatial Pixel', fontsize=28.6)
    profile.set_ylabel((r'Summed Bkg-Subtracted Signal [$10^3\,e^{-}$]' if profile_sky_available
                       else r'Median Signal [$10^3\,e^{-}$] (sky included)'), fontsize=28.6)
    # Summation rule and row ranges stay in profile-display.json and the report
    # caption; the figure keeps a short title.
    profile.set_title('Spatial profile' if profile_sky_available
                      else 'Spatial profile (sky included)')
    if profile_sky_available:
        profile.axhline(0, color='0.5', lw=.8, zorder=0)
    profile.legend(ncol=3, fontsize=23.4);profile.grid(False)
    fig.suptitle(title)
    save_qc(fig,output,'profiles',exposure.result['object'],tick_fontsize=18,legend_fontsize=18)
    plt.close(fig)
    save_json(Path(output)/'profile-display.json', {
        'coordinates':'raw_detector_pixels_zero_based', 'candidate_reference_raw_y':int(y0+ny//2),
        'strength_measure':'median electrons sampled along saved trace; not detection S/N',
        'sky_subtracted':profile_sky_available,
        'profile_statistic':('sum of pixel-wise background residuals over the same common valid spectral rows at each displayed spatial x; no filling, smoothing or coverage rescaling'
                             if profile_sky_available else 'median over selected spectral rows at each fixed spatial x; no fitted background'),
        'background_source':background['provenance'] if background else None,
        'profile_x_limits':list(profile_xlimits),
        'profile_background_x_limits':list(supported_xlimits) if background else None,
        'profile_row_ranges':row_ranges,
        'missing_pixel_policy':'exclude a row at every displayed x if any supported non-dead column is missing; fully missing columns remain NaN',
        'traces':[{'candidate':i+1,'rank':rank+1,'color':colors[i],'linestyle':TRACE_STYLES[i%4],
                   'median_electrons':strengths[i] if np.isfinite(strengths[i]) else None} for rank,i in enumerate(order)],
        'display_only':True,'all_profile_samples_plotted':True,
        'image_display':image_displays,
        'ylim_excluded_raw_x_by_profile':exclusions,
        'outlier_rule':'negative deviation from 7-pixel running median >10 MAD-sigma and <=2 columns; positive spikes require >20 MAD-sigma prominence and half-prominence width <=2 pixels, with <=3-column >10-sigma core; protect every saved trace envelope +/-3 pixels; display limits only',
        'slit_edge_margin_columns':SLIT_EDGE_MARGIN,
        'slit_edge_rule':f'the outermost {SLIT_EDGE_MARGIN} unprotected columns on each side are excluded from the limit estimate only; they remain plotted',
        'ylim':limits, 'ylim_rule':('20 percent span below retained minimum; include zero; 10 percent above maximum'
                                  if profile_sky_available else '10 percent outward padding of retained extrema'),
        'display_signal_unit':'10^3 electrons', 'display_signal_divisor':1000.,
        'y_tick_format':'plain numbers in 10^3 electrons',
    })


@house_style
def acquisition_images(exposure, output):
    """Full acquisition and separate zoom, with the documented slit direction."""
    from .figure_style import save_qc
    from .acquisition_slit import draw_slit_orientation
    import matplotlib.pyplot as plt
    raw = Path(exposure.frame['path']); header = fits.getheader(raw)
    records = []
    if header.get('ESO OBS ID') is None:
        return records
    for path in sorted(raw.parent.glob('*.fits')):
        h = fits.getheader(path)
        if (h.get('ESO OBS ID') != header['ESO OBS ID']
                or h.get('ESO TPL ID') != 'EFOSC_img_acq_MoveToSlit' or h.get('NAXIS') != 2):
            continue
        data = fits.getdata(path).astype(float); ny,nx=data.shape
        fig,(full,detail)=plt.subplots(1,2,figsize=(20,11),constrained_layout=True)
        half=min(180,ny//2,nx//2);y0=ny//2-half;x0=nx//2-half
        zoom=data[y0:y0+2*half,x0:x0+2*half]
        normalization=image_normalization(zoom,cmap='RdBu')
        _image(full,data,normalization=normalization,cmap='RdBu')
        _image(detail,zoom,[x0-.5,x0+2*half-.5,y0-.5,y0+2*half-.5],normalization=normalization,cmap='RdBu')
        zoom_bounds=mark_zoom_region(full,detail)
        detail.set_title('Acquisition zoom')
        full.set_title('Acquisition detector')
        orientation=draw_slit_orientation(detail)
        for ax in (full,detail):
            ax.set_xlabel('Acquisition raw x');ax.set_ylabel('Acquisition raw y')
        fig.suptitle(f"{exposure.result['object']} -- {path.name}",fontsize=20)
        filename=f'acquisition-{len(records)+1}.png'
        save_qc(fig,output,Path(filename).stem,exposure.result['object'],tick_fontsize=27);plt.close(fig)
        records.append(dict(path=str(path),sha256=sha256(path),image=filename,
            zoom_raw_bounds_xy=zoom_bounds,image_display=normalization[1],slit_orientation=orientation,
            slit_overlay_on_zoom_only=True,has_celestial_wcs=bool(WCS(h).has_celestial),date_obs=h.get('DATE-OBS')))
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
    images=['science.png','traces.png','profiles.png']+[a['image'] for a in review['acquisitions']]
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


def build_reviewed_qc(run, product, output, reference_root=None):
    """Show the newly fitted background with the original, stable C1/C2/C3 IDs."""
    exposure = Exposure(run, product, reference_root)
    selection = exposure.result['target']['reviewed_source']
    original = FailedExposure(selection['parent_run'], selection['raw_name'], reference_root)
    if (original.hashes['raw'] != exposure.hashes['raw'] or original.window != exposure.window
            or not np.array_equal(original.images['data'], exposure.images['data'], equal_nan=True)
            or not np.array_equal(original.images['waveair'], exposure.images['waveair'], equal_nan=True)):
        raise ValueError('reviewed QC no longer matches the original candidate geometry')
    # Display original candidate paths without altering any saved science array.
    exposure.candidates = original.candidates
    for key in ('found_traces','found_names'):
        exposure.images[key] = original.images[key]
    output = Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    middle = exposure.window.shape[0]//2
    confirmed=selection['identity']['method']=='operator_visual'
    identity_label=(f"C{selection['identity']['candidate']} verified by operator" if confirmed else
                    f"C{selection['identity']['candidate']} background reviewed; target identity unverified")
    review = dict(status='running', identity=identity_label,
        object=selection['object'], raw_name=selection['raw_name'], raw_path=exposure.frame['path'],
        parent_run=str(exposure.run), input_sha256=exposure.hashes,
        identification=selection['identity'], candidate_geometry_parent=str(original.run),
        coordinates='raw_detector_pixels_zero_based', candidates=[], acquisitions=[])
    for number, trace in enumerate(_traces(exposure),1):
        review['candidates'].append(dict(number=number,anchor_raw_x=float(trace[middle]),
            anchor_raw_y=middle+exposure.window.origin[0]))
    plot_exposure(exposure, output)
    review['acquisitions'] = acquisition_images(exposure, output)
    refreshed = Exposure(run,product,reference_root)
    if refreshed.hashes != exposure.hashes:
        raise ValueError('reviewed exposure changed while creating QC')
    for acquisition in review['acquisitions']:
        if sha256(Path(acquisition['path'])) != acquisition['sha256']:
            raise ValueError('acquisition input changed during QC')
    review.update(status='complete', raw_and_calibration_inputs_unchanged=True,
                  qc_source_sha256=sha256(Path(__file__)))
    save_json(output/'review.json',review)
    figures = ['science','traces','profiles']
    figures += [Path(a['image']).stem for a in review['acquisitions']]
    html = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>body{font:16px system-ui;max-width:1200px;margin:24px auto;padding:16px}img{width:100%}</style>'
        f'<h1>{escape(review["object"])}: {escape(review["identity"])}</h1>'
        f'<p>{escape(review["raw_name"])}</p><p>{escape(selection["identity"]["evidence"])}</p>'
        '<p>Original candidate IDs are retained. Residual panels and summed profiles use the newly fitted '
        'two-sided PypeIt background. '
        + ('Identification is visual; no automatic astrometric match is claimed.' if confirmed else
           'Background geometry was reviewed; the source identity remains unverified.')+'</p>'
        '<p><a href="review.json">Review record</a> · <a href="profile-display.json">Profile details</a></p>'
        + ''.join(f'<img src="{name}.png" alt="{escape(name)}">' for name in figures))
    (output/'index.html').write_text(html)
    return review
