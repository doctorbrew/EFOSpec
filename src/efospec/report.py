"""Offline Fieldnotes report, assembled from recorded reductions and figures."""
import hashlib
from html import escape
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

from .inventory import sha256
from .naming import source_order


PIPELINE_STAGES = (
    ('Inventory & association', 'EFOSpec / Astropy',
     'Read headers, hash inputs, preserve legacy names, and choose archived references.'),
    ('Detector preparation', 'EFOSpec / NumPy',
     'Legacy rapid trim, gain conversion and target crop. No bias, flat, dark or overscan correction.'),
    ('Wavelength calibration', 'EFOSpec / NumPy + SciPy',
     'Fit a 2D polynomial to archived IRAF arc IDs. Measure a shift from sky lines 5577 and 6300 Å; reserve 6364 Å as a check.'),
    ('Trace, sky & extraction', 'PypeIt',
     'PypeItImage and slit geometry; FindObjects detection/tracing and global sky; Extract sky/object fitting, optimal and boxcar extraction with uncertainties. Explicit manual sky regions retain their global sky fit.'),
    ('Flux calibration', 'EFOSpec / archived references',
     'Apply the archived sensitivity and La Silla extinction curve, with gain, exposure and wavelength-dispersion factors. No new PypeIt sensitivity fit.'),
    ('Products', 'PypeIt + EFOSpec',
     'PypeIt writes native spec1d counts in vacuum wavelengths. Its air/vacuum utilities are used; EFOSpec rebins flux and diagonal variance to air wavelengths and writes legacy FITS/ASCII products.'),
    ('Diagnostics & webpage', 'EFOSpec / Matplotlib + HTML',
     'Render the saved spectrum, sky-subtracted 2D image and spatial profiles, with optional IRAF comparison. No reduction is performed in the webpage.'),
)

NATIVE_STAGES = (
    ('Inventory & association', 'EFOSpec / Astropy',
     'Hash raw inputs and associate matching biases, flats, arcs and the selected observed standard.'),
    ('Detector preparation', 'PypeIt',
     'Build raw bias and flat masters; process detector images with propagated variance and a cosmic-ray mask.'),
    ('Wavelength calibration', 'EFOSpec + PypeIt',
     'Identify physical He–Ar wavelengths in the raw arc; fit wavelength and tilt maps. Require physical bounds and line holdouts. Correct science flexure with 5577 and 6300 Å; check 6363 Å independently.'),
    PIPELINE_STAGES[3],
    ('Flux calibration', 'PypeIt + physical standard reference',
     'Fit a new sensitivity curve from the observed standard and its physical flux reference; apply La Silla extinction. No archived IRAF sensitivity or arc IDs.'),
    *PIPELINE_STAGES[5:],
)


def reduction_methods(manifest):
    """Describe the engines actually recorded, including native joint revisions."""
    results = manifest['results']
    native = any(r.get('calibration', {}).get('mode') == 'native_raw_only' for r in results)
    native = native or manifest.get('method', '').startswith('native_raw_calibration')
    archived = any(not r.get('calibration') for r in results)
    joint = manifest.get('method') == 'fixed_profile_joint_extraction'
    rows = list(NATIVE_STAGES if native else PIPELINE_STAGES)
    if native and archived:
        rows = [(f'Raw-only: {stage}', owner, detail) for stage, owner, detail in NATIVE_STAGES]
        rows += [(f'Archive bridge: {stage}', owner, detail) for stage, owner, detail in PIPELINE_STAGES]
        summary = 'This report contains both raw-only and archive-bridge calibrations; see each product’s source details.'
    elif native:
        summary = 'Calibration uses raw biases, flats and arcs, plus an observed spectrophotometric standard. No IRAF/PyRAF runtime or archived IRAF calibration products are used.'
    else:
        summary = 'The calibration bridge uses archived IRAF references; IRAF/PyRAF is not executed.'
    if joint:
        rows = [(stage, 'EFOSpec / weighted linear fit',
                 'Fit fixed source profiles jointly with a polynomial background. Save cross-source covariance and background alternatives. Errors are conditional on the selected profiles and background.')
                if stage.endswith('Trace, sky & extraction') else (stage, owner, detail)
                for stage, owner, detail in rows]
        summary += ' Source separation uses the experimental EFOSpec fixed-profile joint solver; PypeIt supplies the spectrum file format.'
        caption = 'Blue shading: regions used to select the polynomial background degree. Red shading: geometric boxcar aperture, not joint-fit weights.'
    else:
        summary += ' PypeIt handles tracing, sky modelling and extraction.'
        caption = 'Blue shading: global-sky input selection before iterative rejection. Red shading in the spatial profiles: geometric boxcar aperture, not optimal-extraction weights. Opacity follows the selected fraction within each wavelength bin.'
    if manifest.get('methodology_checks'):
        rows.insert(1,('Calibration readiness','EFOSpec',
            'Record matching raw arc/bias/flat and standard candidates for every setup, including skipped configurations. Availability does not enable unsupported setups.'))
        rows.append(('Wavelength review','PypeIt + EFOSpec',
            'Save sky spectra, fitted line models and failure gates. Compare with PypeIt sky-template correlation in vacuum coordinates; comparison shifts are not applied.'))
        rows.append(('Review products','PypeIt + EFOSpec',
            'Write PypeIt spec2d diagnostics for extracted or source-ambiguous windows. Preserve target uncertainty and saved recipes; no automatic selection of a nearby trace.'))
    if manifest.get('wavelength_policy')=='provisional_arc_only':
        rows=[(stage,owner,'Retain raw arc wavelengths. Science sky validation failed; no flexure correction is applied.')
              if stage=='Wavelength calibration' else (stage,owner,detail) for stage,owner,detail in rows]
        summary+=' PROVISIONAL: science wavelengths remain unvalidated.'
    return rows, summary, caption

CSS = """
.qc-unvalidated{border-left:3px solid #b42318;padding-left:12px}.qc-unvalidated>summary,.qc-status-bad{color:#b42318;font-weight:600}
:root{--paper:#f7f6f0;--panel:#fffef9;--forest:#244d3d;--ink:#29362e;--quiet:#616a61;--line:#dfe2d7;--serif:'Iowan Old Style','Palatino Linotype',Georgia,serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 'Avenir Next',Avenir,'Helvetica Neue',Arial,sans-serif}
main{max-width:1680px;margin:auto;padding:28px 32px 60px}a{color:var(--forest);text-underline-offset:3px}a:hover{color:#497c61}a:focus-visible,summary:focus-visible{outline:2px solid var(--forest);outline-offset:4px}
.masthead{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:24px}.brand{font:26px var(--serif);color:var(--forest)}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:11px;color:var(--quiet)}
h1,h2,h3{font-family:var(--serif);font-weight:400;color:var(--forest);line-height:1.15}h1{font-size:38px;margin:4px 0 12px}h2{font-size:27px;margin:0}h3{font-size:22px;margin:0}.muted,.caption{color:var(--quiet)}.caption{font-size:12px}.intro{display:flex;align-items:baseline;justify-content:space-between;gap:16px}.intro p{margin:0 0 18px}
.badge{display:inline-block;border-radius:20px;padding:3px 10px;background:#ebeee7;color:var(--forest);font-size:12px}.note{border-left:3px solid #a78d63;padding:8px 14px;background:#f3eee3;font-size:13px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:8px;background:var(--panel);margin:0 0 18px}table{border-collapse:collapse;width:100%;white-space:nowrap;font-variant-numeric:tabular-nums}th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--quiet);text-align:left;background:#eef0e8}th,td{padding:10px 16px;border-bottom:1px solid var(--line)}tr:last-child td{border-bottom:0}tbody tr:hover{background:#f0f2e9}.target-link{font-weight:600;text-decoration:none}.num{text-align:right}
.target{scroll-margin-top:16px;border-top:1px solid var(--line);padding-top:24px;margin-top:36px}.target-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:14px}.target-head p{margin:5px 0}.plots{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.plot{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden}.plot figcaption{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;border-bottom:1px solid var(--line);gap:8px}.plot h3{font-size:20px}.plot-links{font-size:12px;white-space:nowrap}.plot img{width:100%;height:auto;display:block;background:white}.plot-image{display:flex;align-items:center;aspect-ratio:1;background:white}.placeholder{min-height:180px;display:grid;place-content:center;text-align:center;padding:20px;color:var(--quiet)}.methods{margin-top:36px;border-top:1px solid var(--line);padding-top:24px}.methods table{white-space:normal}.methods td{vertical-align:top}.methods td:first-child{min-width:170px}.methods td:nth-child(2){min-width:180px}details{margin:18px 0}summary{cursor:pointer;color:var(--forest)}footer{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding-top:16px;margin-top:32px;color:var(--quiet);font-size:12px}
@media(max-width:800px){main{padding:18px 12px 40px}.intro{display:block}h1{font-size:30px}.plot figcaption{align-items:flex-start;flex-direction:column;padding:10px}.plot h3{font-size:18px}.plots{gap:8px}.target-head{align-items:flex-start}.masthead{gap:12px}}
@media(max-width:560px){.plots{grid-template-columns:repeat(3,280px);overflow-x:auto;padding-bottom:12px;scroll-snap-type:x proximity}.plot{scroll-snap-align:start}.target-head{display:block}footer{display:block}}
"""


def local_url(path, run):
    """Only link existing files inside this run; URLs stay portable and escaped."""
    path = Path(path).resolve()
    relative = path.relative_to(run)
    if not path.is_file():
        raise FileNotFoundError(path)
    return quote(relative.as_posix(), safe='/')


def write_report(run_directory, *, generation_error=None):
    run = Path(run_directory).resolve()
    manifest = json.loads((run/'run.json').read_text())
    plot_dir = run/'style-preview'
    records = []
    for path in sorted(plot_dir.glob('FitSpectrum_*.json')):
        try:
            records.append(json.loads(path.read_text()))
        except (ValueError, OSError):
            continue  # Show missing figures, never an unrelated/stale record.
    rows, sections, missing = [], [], []
    for result in sorted(manifest['results'], key=source_order):
        # Resolve by basename so a whole run can be moved without editing JSON.
        product = run/'products'/Path(result['product']).name
        digest = sha256(product)
        matches = [r for r in records if any(
            Path(p).name == product.name and h == digest
            for p, h in r.get('input_sha256', {}).items())]
        record = matches[-1] if matches else {}
        files = {Path(p).name: plot_dir/Path(p).name for p in record.get('outputs', [])}
        anchor = 'exposure-'+hashlib.sha256(product.name.encode()).hexdigest()[:12]
        target, grism = escape(result['object']), escape(result['grism'])
        snr = result['median_native_snr_4000_8500']
        exposure = result['exptime_s']
        downloads = f'<a href="{local_url(product, run)}">FITS</a>'
        if product.with_suffix('.asci').is_file():
            downloads += f' · <a href="{local_url(product.with_suffix(".asci"), run)}">ASCII</a>'
        rows.append(f'<tr><td><a class="target-link" href="#{anchor}">{target}</a></td>'
                    f'<td>{grism}</td><td class="num">{exposure:.0f}</td><td class="num">{snr:.1f}</td>'
                    f'<td><a href="#{anchor}">View plots ↗</a></td><td>{downloads}</td></tr>')
        cards = []
        for prefix, title in (('FitSpectrum_', 'Spectrum'), ('FitTrace_', '2D spectrum before and after sky subtraction'),
                              ('FitSpatialProfile_', 'Spatial profile')):
            jpgs = [p for n, p in files.items() if n.startswith(prefix) and p.suffix == '.jpg' and p.is_file()]
            if len(jpgs) == 1:
                jpg = jpgs[0]
                url = local_url(jpg, run)
                links = f'<a href="{url}" target="_blank" rel="noopener">JPG ↗</a>'
                if jpg.with_suffix('.pdf').is_file():
                    links += f' · <a href="{local_url(jpg.with_suffix(".pdf"), run)}">PDF</a>'
                content = (f'<a class="plot-image" href="{url}" target="_blank" rel="noopener" '
                           f'aria-label="Enlarge {target} {title}"><img loading="lazy" decoding="async" '
                           f'src="{url}" alt="{target} · {grism} · {title}"></a>')
            else:
                missing.append({'product': product.name, 'figure': title})
                links = ''
                content = '<div class="placeholder">Figure not generated yet.<br>Run the report command to create it.</div>'
            cards.append(f'<figure class="plot"><figcaption><h3>{title}</h3>'
                         f'<span class="plot-links">{links}</span></figcaption>{content}</figure>')
        association = result.get('target', {}).get('association')
        notice = ('<p class="note">Target identity is unverified: extraction used the nominal acquisition position.</p>'
                  if association not in {'historical_aperture', 'operator_selected'} else '')
        if result.get('status')=='PROVISIONAL':
            notice+='<p class="qc-status-bad">Provisional flux; science wavelengths unvalidated. '+escape(result.get('interpretation',''))+'</p>'
        if result.get('valid_flux_fraction',1.) < .8:
            notice += (f'<p class="note">Only {100*result["valid_flux_fraction"]:.0f}% '
                       'of output flux bins are valid. Unsupported bins remain masked; inspect extraction and response coverage.</p>')
        sections.append(f'<section class="target" id="{anchor}"><div class="target-head"><div>'
                        f'<span class="eyebrow">EFOSC2 / {grism}</span><h2>{target}</h2>'
                        f'<p class="caption">{escape(result["date_obs"])} UTC · {exposure:.0f} s · '
                        f'Median SNR {snr:.1f} per native pixel</p></div><a href="#observations">Back to table ↑</a>'
                        f'</div>{notice}<div class="plots">{"".join(cards)}</div></section>')
    errors = manifest.get('errors', [])
    skips = manifest.get('skipped', [])
    for error in errors:
        rows.append(f'<tr><td>{escape(error.get("object", "Unknown"))}</td>'
                    '<td colspan="5">Reduction failed; see run notes below.</td></tr>')
    night = escape(Path(manifest.get('input_dir', '')).name or run.name)
    problem = ''
    if generation_error or missing:
        problem = ('<p class="note">Plot generation is incomplete. '
                   + escape(generation_error or 'Some figures are missing; regenerate the report.')
                   + (' <a href="report-generation.log">Generation log</a>.' if (run/'report-generation.log').exists() else '')
                   + '</p>')
    stages, method_summary, shading_caption = reduction_methods(manifest)
    method_rows = ''.join('<tr>'+''.join(f'<td>{escape(cell)}</td>' for cell in row)+'</tr>' for row in stages)
    failures = ''.join(f'<li>{escape(e.get("object", Path(e.get("path", "")).name))}: '
                       f'{escape(e.get("error", e.get("reason", "")))}</li>' for e in errors+skips)
    limitations = ''.join(f'<li>{escape(note)}</li>' for note in manifest.get('limitations', []))
    check_links=[]
    for path in sorted((run/'checks').glob('*/check.json')):
        record=json.loads(path.read_text())
        label=record['metadata'].get('object',path.parent.name)+' / '+path.parent.name
        plot=path.parent/'wavelength.png'
        check_links.append('<details><summary>'+escape(label)+' — '+escape(record['status'])+'</summary>'
            +f'<p><a href="{local_url(path,run)}">Measurements and decisions</a></p>'
            +(f'<img style="max-width:100%" src="{local_url(plot,run)}" alt="Wavelength checks">' if plot.exists() else '')+'</details>')
    if (run/'setup-checks.json').exists():
        check_links.insert(0,'<p><a href="setup-checks.json">Raw calibration readiness by exposure</a></p>')
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Nightly LOG - NTT/EFOSC2 (ePESSTO+) · {night}</title>
<style>{CSS}</style></head><body><main>
<div class="masthead"><span class="brand">Nightly LOG - NTT/EFOSC2 (ePESSTO+)</span>
<span class="eyebrow">EFOSC2 · reduction notebook</span></div>
<div class="intro"><div><span class="eyebrow">Observing night / {night}</span><h1>The night's spectra.</h1></div>
<p><span class="badge">Experimental reduction</span> &nbsp; {len(manifest['results'])} reduced · {len(errors)} failed · {len(skips)} skipped</p></div>
<div id="observations" class="table-wrap"><table><thead><tr><th>Target</th><th>Grism</th>
<th class="num">Exposure (s)</th><th class="num">Median SNR</th><th>Figures</th><th>Products</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="6">No reduced exposures.</td></tr>'}</tbody></table></div>
<p class="caption">SNR per native pixel over 4000–8500 Å. Click a target to inspect all three plots; click a plot to enlarge it.</p>
{problem}{''.join(sections)}
<section class="methods"><span class="eyebrow">Methods / engine boundaries</span><h2>How this reduction was made.</h2>
<p>{escape(method_summary)}</p>
<div class="table-wrap"><table><thead><tr><th>Stage</th><th>Implementation</th><th>What happens</th></tr></thead><tbody>{method_rows}</tbody></table></div>
<p class="caption">{escape(shading_caption)}</p>
{''.join(check_links)}
<details><summary>Run notes & limitations</summary><ul>{failures}{limitations}</ul></details></section>
<footer><span>ePESSTO+ / EFOSpec · PypeIt {escape(str(manifest.get('pypeit_version', 'not recorded')))}</span>
<a href="run.json">Source details ↗</a></footer></main></body></html>'''
    destination = run/'index.html'
    temporary = destination.with_suffix('.html.tmp')
    temporary.write_text(page)
    temporary.replace(destination)
    plot_dir.mkdir(exist_ok=True)
    (plot_dir/'index.html').write_text('<!doctype html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=../index.html">'
        '<a href="../index.html">Open the ePESSTO+ reduction report</a>')
    status = {'path': str(destination), 'status': 'incomplete' if missing or generation_error else 'complete',
              'missing_figures': missing, 'generation_error': generation_error}
    (run/'report.json').write_text(json.dumps(status, indent=2)+'\n')
    return status


def build_report(run_directory, *, plot_python=None, render_plots=True):
    """Render with the requested plotting Python, then always emit the HTML.

    A plotting failure is reported separately and cannot erase science products.
    Use --existing-plots to rebuild HTML alone, including on a moved run directory.
    """
    run = Path(run_directory).resolve()
    manifest = json.loads((run/'run.json').read_text())
    error = None
    if render_plots and manifest['results']:
        python = (plot_python or os.environ.get('EFOSPEC_PLOT_PYTHON')
                  or os.environ.get('EPESSTO_PLOT_PYTHON') or sys.executable)
        script = Path(__file__).resolve().parents[2]/'scripts/preview_spectrum_style.py'
        try:
            with (run/'report-generation.log').open('w') as log:
                completed = subprocess.run([str(python), str(script), '--run', str(run)],
                                           stdout=log, stderr=subprocess.STDOUT, check=False)
            if completed.returncode:
                error = (f'Plot renderer exited with status {completed.returncode}. '
                         'Use --plot-python with SciencePlots, pypalettes, Matplotlib and LaTeX available.')
        except OSError as exc:
            error = f'Could not start the plot renderer: {exc}'
    if render_plots and any((run/'checks').glob('*/check.json')):
        python = plot_python or os.environ.get('EFOSPEC_PLOT_PYTHON') or sys.executable
        try:
            with (run/'check-plots.log').open('w') as log:
                completed=subprocess.run([str(python),'-m','efospec.check_plots',str(run)],
                    stdout=log,stderr=subprocess.STDOUT,check=False)
            if completed.returncode:
                error=(error+' ' if error else '')+'Wavelength check plotting failed; see check-plots.log.'
        except OSError as exc:
            error=(error+' ' if error else '')+f'Could not render wavelength checks: {exc}'
    return write_report(run, generation_error=error)
