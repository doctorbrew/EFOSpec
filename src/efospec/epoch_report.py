"""Portable, read-only Fieldnotes assembled from one epoch's saved evidence."""
import argparse
import base64
from collections import Counter
from datetime import date
from html import escape
import json
from io import BytesIO
from pathlib import Path

from .inventory import sha256
from .naming import source_order
from .report import CSS


def _text(value):
    return escape(str(value))


def _unvalidated(status):
    return any(word in str(status).lower() for word in
               ('fail', 'unvalidated', 'unsupported', 'unavailable', 'missing', 'unknown'))


def _table(headings, rows):
    return ('<div class="table-wrap"><table><thead><tr>'
            + ''.join('<th>'+_text(h)+'</th>' for h in headings)
            + '</tr></thead><tbody>'
            + ''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)
            + '</tbody></table></div>')


class EpochPage:
    def __init__(self, root):
        self.root = root.resolve()
        self.warnings = []
        self.images = 0

    def read(self, path):
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            self.warnings.append(f'{path.name}: {exc}')
            return {}

    def data(self, path, mime):
        # Embed only this date's saved artifacts, including relocated products.
        path.resolve().relative_to(self.root)
        return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode('ascii')

    def download(self, path, label):
        if not path.is_file():
            return ''
        mime = {'.json':'application/json', '.csv':'text/csv', '.asci':'text/plain',
                '.log':'text/plain', '.pdf':'application/pdf'}.get(path.suffix, 'application/octet-stream')
        return f'<a download="{_text(path.name)}" href="{self.data(path, mime)}">{_text(label)}</a>'

    def figure(self, path, title, *, full_width=False):
        if not path or not path.is_file():
            return '<p class="note">'+_text(title)+': figure unavailable.</p>'
        self.images += 1
        # Small web previews retain the existing figure layout and styling.
        # Publication PDF/JPG files are read-only and remain at full resolution.
        from PIL import Image
        path.resolve().relative_to(self.root)
        with Image.open(path) as source:
            preview = source.convert('RGB')
            preview.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            encoded = BytesIO()
            preview.save(encoded, format='JPEG', quality=85, optimize=True)
        url = 'data:image/jpeg;base64,'+base64.b64encode(encoded.getvalue()).decode('ascii')
        css_class = 'plot full-width' if full_width else 'plot'
        return (f'<figure class="{css_class}"><figcaption>{_text(title)}</figcaption>'
                f'<button class="enlarge" type="button" aria-label="Enlarge {_text(title)}">'
                f'<img loading="lazy" src="{url}" alt="{_text(title)}"></button></figure>')

    def spectra(self, run_dir, run):
        records = [self.read(p) for p in sorted((run_dir/'style-preview').glob('FitSpectrum_*.json'))]
        sections = []
        for i, result in sorted(enumerate(run.get('results', [])), key=lambda item: source_order(item[1])):
            product = run_dir/'products'/Path(result.get('product', '')).name
            digest = sha256(product) if product.is_file() else None
            matches = [r for r in records if digest and any(
                Path(p).name == product.name and h == digest for p, h in r.get('input_sha256', {}).items())]
            record = matches[-1] if matches else {}
            outputs = [run_dir/'style-preview'/Path(p).name for p in record.get('outputs', [])]
            title = f"{result.get('object', 'Unknown')} · {result.get('grism', '')} · {result.get('slit', '')}"
            cards = []
            for prefix, name in [('FitSpectrum_', 'Spectrum'), ('FitTrace_', '2D trace'), ('FitSpatialProfile_', 'Spatial profile')]:
                images = [p for p in outputs if p.name.startswith(prefix) and p.suffix == '.jpg']
                cards.append(self.figure(images[0] if len(images) == 1 else None, title+' / '+name))
            downloads = ' · '.join(filter(None, [self.download(product, 'FITS'), self.download(product.with_suffix('.asci'), 'ASCII')]))
            association = result.get('target', {}).get('association')
            identity = '' if association in {'historical_aperture', 'operator_selected'} else (
                ' · <span title="The extracted detector trace has not been independently matched to the named target; extraction itself succeeded.">Target identity unverified</span>')
            if result.get('target',{}).get('identity',{}).get('method') == 'operator_visual':
                identity = ' · C'+str(result['target']['identity']['candidate'])+' identified visually by operator'
            sections.append(f'<article class="exposure" id="spectrum-{i}"><h3>{_text(title)}</h3>'
                f'<p class="caption">{_text(result.get("date_obs", ""))} UTC{identity} · {downloads}</p>'
                f'<div class="plots">{"".join(cards)}</div></article>')
        return ''.join(sections) or '<p>No spectra recorded in this revision.</p>'

    def observations(self, revision, run):
        targets = self.read(revision/'night.json').get('targets')
        outcomes = {}
        for group, label in [('results', 'Spectrum'), ('errors', 'Failed'), ('skipped', 'Unsupported')]:
            for i, result in enumerate(run.get(group, [])):
                raw = Path(result.get('raw', result.get('path', ''))).name
                reason = {'sky_flexure_unreliable':'Sky-line check', 'source_selection_required':'Choose source',
                          'background_support_required':'Review background',
                          'unsupported_setup':'Unsupported setup'}.get(result.get('code'), label)
                outcomes[raw] = f'<a href="#spectrum-{i}">Spectrum ↓</a>' if group == 'results' else _text(reason)
        rows = []
        for frame in sorted(self.read(revision/'observing-log.json').get('frames', []), key=source_order):
            if frame.get('role') not in {'science', 'standard_candidate'} or 'duplicate_of' in frame:
                continue
            h, setup = frame['metadata'], frame['setup']
            raw = Path(frame['path']).name
            start = str(h.get('DATE-OBS', '')).replace('T', ' ')
            try:
                seconds = round(float(h.get('EXPTIME') or 0))
            except (ValueError, TypeError, OverflowError):
                seconds = h.get('EXPTIME', 'Unknown')
            rows.append([_text(h.get('OBJECT', '')), _text(start),
                'Standard' if frame['role'] == 'standard_candidate' else 'Science',
                _text(setup.get('grism', ''))+' / '+_text(setup.get('filter', '')),
                _text(setup.get('slit', '')), _text(seconds),
                outcomes.get(raw, 'Outside selected targets' if targets and h.get('OBJECT') not in targets else 'Not reduced')])
        return _table(['Target', 'UTC start', 'Role', 'Setup', 'Slit', 'Seconds', 'Result'], rows)

    def problems(self, run, run_dir=None):
        groups = {}
        for item in run.get('errors', [])+run.get('skipped', []):
            code = item.get('code', 'unknown')
            groups.setdefault(code, []).append(item)
        rows = []
        for code, items in groups.items():
            names = Counter(x.get('object', 'Unknown') for x in sorted(items, key=source_order))
            targets = ', '.join(k+(f' ×{v}' if v > 1 else '') for k, v in names.items())
            detail = {'sky_flexure_unreliable':'Sky lines did not pass the flexure checks.',
                'source_selection_required':'Multiple traces; target selection needs review.',
                'background_support_required':'Insufficient clean two-sided background; inspect the saved trace geometry.',
                'unsupported_setup':'This archive reduction does not support the recorded setup.'}.get(code, items[0].get('reason', items[0].get('error', code)))
            rows.append([_text(code), len(items), _text(targets), _text(detail)])
        content=_table(['Issue', 'Exposures', 'Targets', 'Meaning'], rows) if rows else '<p>No recorded reduction failures.</p>'
        if run_dir is not None:
            content+=self.wavelength_checks(run_dir)
            readiness=run_dir/'setup-checks.json'
            if readiness.exists():
                content+='<p>'+self.download(readiness,'Raw calibration readiness by exposure')+'</p>'
        return content

    def wavelength_checks(self, run_dir):
        content=''
        records=[(path,self.read(path)) for path in (run_dir/'checks').glob('*/check.json')]
        for path,check in sorted(records,key=lambda item:source_order({
                'object':item[1].get('metadata',{}).get('object',''), 'path':str(item[0])})):
            title=check.get('metadata',{}).get('object',path.parent.name)+' / '+path.parent.name
            status=check.get('status','unknown')
            line=check.get('line_check',{})
            reason=', '.join(line.get('failed_gates',[])) or (
                'Anchor checks passed' if status=='passed' else 'Wavelength correction is not validated')
            if status=='passed' and 'held_out_6363_pass' in line and line['held_out_6363_pass'] is not True:
                status='anchors passed; 6363 check unvalidated'
            comparison=check.get('correlation',{})
            description=('PypeIt correlation: '+str(comparison.get('status','not recorded'))
                +'; comparison only, not an applied correction.')
            css=' class="qc-unvalidated"' if _unvalidated(status) else ''
            content+='<details'+css+'><summary>'+_text(title)+' — '+_text(status)+'</summary>'
            content+='<p>'+_text(reason)+'. '+_text(description)+'</p>'
            content+=self.figure(path.parent/'wavelength.png',title+' / wavelength checks')
            content+='<p>'+self.download(path,'Fit measurements and provenance')+'</p></details>'
        return content

    def qc(self, revision, run):
        packets = {}
        # Current QC wins; retained original packets supply reviewed experiments.
        for folder in [self.root/'QC', revision/'QC']:
            for path in sorted(folder.glob('*/review.json')):
                review = self.read(path)
                if review.get('raw_name'):
                    packets[review['raw_name']] = (path.parent, review)
        current = {Path(e.get('path', '')).name for e in run.get('errors', [])}
        current.update(Path(r['raw']).name for r in run.get('results', []) if r.get('target',{}).get('reviewed_source'))
        sections, backgrounds = [], []
        for raw, (folder, review) in sorted(packets.items(), key=lambda item: source_order(item[1][1])):
            if raw not in current:
                continue
            title = review.get('object', raw)
            original = self.root/'QC'/Path(raw).stem
            cards = []
            for suffix, label in [('science', '2D Spectrum'), ('traces', 'Sky-subtracted 2D spectrum'),
                                  ('profiles', 'Spatial Profile and Trace Identification'),
                                  ('acquisition-1', 'Acquisition 1'), ('acquisition-2', 'Acquisition 2')]:
                matches = sorted(folder.glob(f'FitQC_*_{suffix}.jpg'))
                if matches:
                    cards.append(self.figure(matches[0], title+' / '+label, full_width=suffix=='profiles'))
            candidates = ', '.join(f'C{c.get("number", i+1)}: x={c.get("anchor_raw_x", c.get("raw_spatial_pixel", 0)):.2f}'
                                   for i, c in enumerate(review.get('candidates', [])))
            profile_info = self.read(folder/'profile-display.json')
            summed = profile_info.get('profile_statistic', '').startswith('sum ')
            profile_description = (
                'The spatial profiles sum background-subtracted electrons over the stated y rows at each fixed x. '
                'Background subtraction uses a saved fit; the zero level is not imposed on the curves. '
                if summed else
                'A fitted background is unavailable for these profiles; they show median electrons including sky across the stated y rows at each fixed x. ')
            if profile_info.get('background_source'):
                profile_description += 'The profiles use a retained two-sided PypeIt fit; the 2D panels above retain the parent reduction state. '
            if profile_info.get('profile_background_x_limits'):
                profile_description += 'Curves are shown only within the supported background interval; candidate markers can lie outside it. '
            sections.append(f'<article class="exposure"><h3>{_text(title)}</h3>'
                f'<p class="caption">{_text(raw)} · Identity {_text(review.get("identity", "unverified").lower())}</p>'
                f'<p>{_text(candidates)} <span class="caption">(raw detector pixels)</span></p>'
                '<p class="caption">Raw detector: full frame and extraction window. Candidate traces: saved source paths. '
                'Sky residual: background-subtracted window, shown without and with those paths. '
                'Where no sky fit exists, the plots are labeled as counts including sky. '
                + profile_description +
                'Q2 and Q3 are the second and third quarters of the extraction window along y; '
                'the legend gives inclusive raw-pixel ranges. '
                'Colored markers locate candidates at the middle row.</p>'
                f'<div class="qc-plots">{"".join(cards)}</div>'
                + ('<p class="caption">Trace colors follow decreasing median signal: red, blue, green, brown. '
                   'Candidate IDs remain fixed. '
                   + self.download(folder/'profile-display.json', 'Profile display details')+'</p>'
                   if (folder/'profile-display.json').is_file() else '')+'</article>')
            # Discover saved polynomial experiments; never invent a global C3 recipe.
            rows, background_cards, experiments = [], [], {}
            for path in sorted(set(original.glob('*/background.json')) | set(folder.glob('*/background.json'))):
                result, recipe = self.read(path), self.read(path.parent/'recipe.json')
                if not recipe or recipe.get('input_sha256', {}).get('raw') != review.get('input_sha256', {}).get('raw'):
                    continue
                key = json.dumps([recipe.get('objects'), recipe.get('sky')], sort_keys=True)
                # Named later revisions supersede an identical recipe; retain other choices.
                experiments[key] = (path, result, recipe)
            for path, result, recipe in experiments.values():
                obj = recipe['objects'][0];sky = recipe['sky']
                bands = ', '.join(f'[{a:g}, {b:g})' for a, b in sky.get('include', []))
                rows.append([_text(obj['label']), f'{obj["spat"]:.2f}', _text(sky.get('degree')),
                    _text(bands), f'{100*result.get("valid_spectrum_fraction", 0):.1f}%'])
                if sky.get('degree') == 2:
                    for image in path.parent.glob('FitQC_*_polynomial-background.jpg'):
                        background_cards.append(self.figure(image, title+' / Quadratic background'))
            if rows:
                for image in original.glob('FitQC_*background-order.jpg'):
                    background_cards.insert(0, self.figure(image, title+' / Polynomial order comparison'))
                backgrounds.append(f'<article class="exposure"><h3>{_text(title)}</h3>'
                    '<p class="note">Provisional source selection for this exposure only. Background-subtracted counts; no flux calibration or verified host separation.</p>'
                    + _table(['Candidate', 'Raw x', 'Degree', 'Background x bands', 'Valid spectrum'], rows)
                    + '<div class="qc-plots">'+''.join(background_cards)+'</div></article>')
        return (''.join(sections) or '<p>No source-review packets for this revision.</p>',
                (''.join(backgrounds)+self.local_background_checks(revision,run))
                or '<p>No retained polynomial background experiments for these exposures.</p>')

    def local_background_checks(self, revision, run):
        """Keep geometry-only checks separate from extraction/identity claims."""
        manifest=revision/'reduction/run.json'
        if not manifest.is_file():return ''
        digest=sha256(manifest)
        raw_hashes={Path(r.get('raw',r.get('path',''))).name:
                    r.get('raw_sha256',r.get('diagnostics',{}).get('raw_sha256'))
                    for r in run.get('results',[])+run.get('errors',[])}
        sections=[];seen=set()
        for path in sorted((self.root/'QC').glob('local-background-*/local-background.json'),reverse=True):
            record=self.read(path)
            if record.get('night')!=self.root.name or record.get('parent_manifest_sha256')!=digest:continue
            for target in record.get('targets',[]):
                expected_raw=raw_hashes.get(target.get('raw_name'))
                if not expected_raw or target.get('input_sha256',{}).get('raw')!=expected_raw:continue
                if target['raw_name'] in seen:continue
                seen.add(target['raw_name'])
                name=target['object'];directory=path.parent/name
                directory.resolve().relative_to(self.root)
                rows=[]
                for case in target.get('cases',[]):
                    bands=', '.join(f'[{a}, {b})' for a,b in case.get('midrow_bands',[])) or 'Unavailable'
                    status=(('Fits expanded window' if case.get('expanded_window') else 'Fits saved window') if case['status']=='geometry_pass' else 'Insufficient two-sided space')
                    rows.append([f'C{case["candidate"]}',f'{case["raw_x"]:.2f}',case.get('selection',{}).get('actual_width_spatial_pixels',case['width_pixels']),
                                 _text(bands),status])
                figures=[];extractions=[];downloads=[]
                for case in target.get('cases',[]):
                    for trial in case.get('extractions',[]):
                        if trial['status']=='extracted_unverified':
                            result=trial['results'][0];fit=result['processing']['background_fit']
                            extractions.append([f'C{case["candidate"]}',trial['degree'],'Extracted · identity unverified',
                                f'{100*result["valid_flux_fraction"]:.1f}%',str(fit['minimum_side_samples'])])
                            recipe_path=path.parent/trial['recipe'];trial_dir=recipe_path.with_suffix('')
                            sidecar=self.read(trial_dir/'qa/local-background-figure.json')
                            saved=list((trial_dir/'native').glob('*_images.npz'))
                            if len(saved)==1 and sidecar.get('images_sha256')==sha256(saved[0]):
                                for filename,digest_image in sidecar.get('figures',{}).items():
                                    image=trial_dir/'qa'/Path(filename).name
                                    if image.is_file() and sha256(image)==digest_image:
                                        figures.append(self.figure(image,f'{name} / C{case["candidate"]}, degree {trial["degree"]}'))
                            product=trial_dir/'products'/Path(result['product']).name
                            downloads.append(self.download(product,f'C{case["candidate"]} degree {trial["degree"]} FITS'))
                        else:
                            extractions.append([f'C{case["candidate"]}',trial['degree'],_text(trial.get('error','Failed')),'—','—'])
                for filename,expected in target.get('figures',{}).items():
                    image=directory/Path(filename).name
                    if not image.is_file() or sha256(image)!=expected:
                        self.warnings.append(f'{name}: local-background figure is missing or changed')
                        continue
                    figures.append(self.figure(image,name+' / Local background geometry'))
                note=('Geometry checks only; test widths are spatial pixels. No new extraction or default change.'
                      if record.get('mode')=='geometry_preflight' else
                      'PypeIt extraction trials; source identities remain unverified. See trial record for failures.')
                sections.append(f'<article class="exposure"><h3>{_text(name)} · Bounded background</h3>'
                    f'<p class="note">{note} Neighbour exclusions use the saved candidates and requested source guard.</p>'
                    +_table(['Candidate','Raw x','Pixels per side','Bands at middle row','Geometry'],rows)
                    +(_table(['Candidate','Degree','Extraction','Valid flux bins','Minimum accepted / side'],extractions) if extractions else '')
                    +'<div class="qc-plots">'+''.join(figures)+'</div>'
                    +'<p>'+' · '.join(filter(None,downloads+[self.download(path,'Trial record')]))+'</p></article>')
        return ''.join(sections)

    def calibrations(self, revision=None):
        rows, seen = [], set()
        paths=sorted((self.root/'calibrations').glob('*/run.json'))
        selected=self.read(revision/'night.json').get('native_calibrations') if revision else None
        if selected:
            selected_path=Path(selected).resolve()/'run.json'
            paths=[selected_path]+[p for p in paths if p.resolve()!=selected_path]
        for path in paths:
            for group in self.read(path).get('groups', []):
                if not group.get('id') or not group.get('setup'):
                    continue
                if group['id'] in seen:
                    continue
                seen.add(group['id']);s = group.get('setup', {})
                wave = group.get('wave_qa', [])
                rms = ', '.join(f'{w["held_out_rms_pixel"]:.3f}' for w in wave if 'held_out_rms_pixel' in w)
                status=group.get('status','unknown').replace('_',' ')
                if any(w.get('independent_science_validation') is False for w in wave):
                    status += '; science unvalidated'
                label=_text(status)
                if _unvalidated(status):label='<span class="qc-status-bad">'+label+'</span>'
                rows.append([_text(s.get('grism', '')), _text(s.get('filter', '')), _text(s.get('slit', '')),
                             label, rms or '—'])
        validations = sorted((self.root/'archive/native-validation').glob('*/validation.json'))
        note = ''
        if validations:
            v = self.read(validations[-1]);counts = Counter(x.get('status', 'unknown') for x in v.get('results', []))
            note = '<p class="caption">Latest retained native diagnostic: '+_text(', '.join(f'{n} {k.replace("_", " ")}' for k, n in counts.items()))
            note += f'; {len(v.get("errors", []))} failed checks. These masters were not used for the archive spectra above.</p>'
        return (_table(['Grism', 'Filter', 'Slit', 'Recorded status', 'Held-out RMS (px)'], rows)+note
                if rows else '<p>No retained native calibration groups.</p>')

    def archive(self, revision):
        paths = list((self.root/'archive').glob('*/run.json'))
        paths += list((self.root/'archive/reductions').glob('*/run.json'))
        paths += [p for p in (self.root/'nightly').glob('*/reduction/run.json') if p.parent.parent != revision]
        rows = []
        for path in sorted(paths):
            run = self.read(path)
            if not any(k in run for k in ['results', 'errors', 'skipped']):
                continue
            rows.append([_text(path.parent.relative_to(self.root)), len(run.get('results', [])),
                         len(run.get('errors', [])), len(run.get('skipped', []))])
        return _table(['Retained reduction', 'Spectra', 'Failed', 'Unsupported'], rows) if rows else '<p>No earlier reductions.</p>'


SCRIPT = """
const dialog = document.querySelector('dialog');
document.querySelectorAll('.enlarge').forEach(button => button.addEventListener('click', () => {
  const source = button.querySelector('img');
  dialog.querySelector('img').src = source.src;
  dialog.querySelector('img').alt = source.alt;
  dialog.showModal();
}));
dialog.querySelector('button').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if(event.target === dialog) dialog.close(); });
"""


def build_epoch_page(night, project_root='.'):
    """Rebuild presentation only; saved science products and recipes stay unchanged."""
    if date.fromisoformat(night).isoformat() != night:
        raise ValueError('observing date must be YYYY-MM-DD')
    root = Path(project_root).resolve()/'runs'/night
    page = EpochPage(root)
    pointer = page.read(root/'nightly/current.json')
    revision = (root/'nightly'/pointer.get('revision', '')).resolve()
    if pointer.get('night') != night or revision.parent != root/'nightly':
        raise ValueError('invalid dated revision pointer')
    state = page.read(revision/'night.json')
    if state.get('night') != night:
        raise ValueError('workflow belongs to a different observing date')
    run = page.read(revision/'reduction/run.json')
    qc, background = page.qc(revision, run)
    titles = [('observations', 'Observing log'), ('spectra', 'Spectra'), ('issues', 'Issues'),
              ('qc', 'Source QC'), ('background', 'Background'), ('calibrations', 'Calibrations'),
              ('archive', 'Archive'), ('records', 'Run record')]
    stage_rows = [[_text(k), _text(v.get('status', 'unknown')), _text(v.get('error', ''))]
                  for k, v in state.get('stages', {}).items()]
    downloads = [page.download(revision/'observing-log.csv', 'Observing log CSV'),
                 page.download(revision/'night.json', 'Workflow JSON'), page.download(revision/'reduction/run.json', 'Reduction JSON')]
    downloads += [page.download(p, p.name) for p in sorted((revision/'logs').glob('*.log'))]
    downloads += [page.download(revision/'reviewed-sources.json','Reviewed source identifications')]
    records = _table(['Stage', 'Status', 'Error'], stage_rows)
    records += '<details><summary>Download logs and provenance</summary><ul>'+''.join('<li>'+d+'</li>' for d in downloads if d)+'</ul></details>'
    records += _table(['Folder', 'Contents'], [['nightly/', 'Current and previous processing revisions'],
        ['QC/', 'Retained source and background experiments'], ['calibrations/', 'Native masters and group selections'],
        ['archive/', 'Earlier reductions, diagnostics and logs']])
    calibration_content=page.calibrations(revision)
    native=revision/'native-validation'
    if (native/'validation.json').exists():
        calibration_content+='<h3>Contemporary raw-calibration checks</h3><p>These checks use the selected native masters. They do not change the archive-calibrated spectra above.</p>'
        calibration_content+=page.download(native/'validation.json','Native validation record')
        calibration_content+=page.wavelength_checks(native)
    content = [page.observations(revision, run), page.spectra(revision/'reduction', run), page.problems(run,revision/'reduction'), qc,
               background, calibration_content, page.archive(revision), records]
    sections = ''.join(f'<section class="target" id="{anchor}"><h2>{title}</h2>{body}</section>'
                       for (anchor, title), body in zip(titles, content))
    stats = ' · '.join(f'{len(run.get(k, []))} {label}' for k, label in [('results','spectra'), ('errors','failed'), ('skipped','unsupported')])
    extra_css = """
    main{max-width:1480px}.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.tabs a{padding:7px 12px;border:1px solid var(--line);border-radius:5px;text-decoration:none;background:var(--panel)}
    .target>h2{margin-bottom:18px}.exposure{margin:24px 0 32px}.qc-plots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
    .qc-plots>.full-width{grid-column:1 / -1}
    .enlarge{display:block;padding:0;border:0;background:transparent;width:100%;cursor:zoom-in}.enlarge:focus-visible{outline:3px solid var(--forest)}
    .plots .plot-image{aspect-ratio:auto}td{white-space:normal}dialog{max-width:95vw;max-height:95vh;padding:10px;border:1px solid var(--line);border-radius:8px}dialog img{display:block;max-width:100%;height:auto}dialog button{position:sticky;top:0;padding:10px 18px;cursor:pointer}dialog::backdrop{background:#172c43bb}
    @media(max-width:800px){.plots{grid-template-columns:1fr;overflow:visible}.qc-plots{grid-template-columns:1fr}.plot{min-width:0}h1{font-size:30px}.intro{display:block}}
    """
    warning = '<p class="note">'+_text('; '.join(page.warnings))+'</p>' if page.warnings else ''
    scope = ('<p class="caption">Selected targets: '+_text(', '.join(state['targets']))
             +'. Other exposures are listed for context; earlier results remain in Archive.</p>') if state.get('targets') else ''
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ePESSTO+ · {night} · EFOSpec</title><style>{CSS}{extra_css}</style></head><body><main>
<header class="masthead"><span class="brand">ePESSTO+ / EFOSpec</span><span class="eyebrow">EFOSC2 · {night}</span></header>
<div class="intro"><div><span class="eyebrow">Observing night</span><h1>{night}</h1></div><p>{stats}</p></div>
<p class="caption">Archive-calibration reduction · {_text(state.get('status', 'unknown'))} · revision {_text(revision.name)}</p>
{scope}
<nav class="tabs" aria-label="Report sections">{''.join(f'<a href="#{a}">{t}</a>' for a,t in titles)}</nav>
{warning}{sections}<footer>EFOSpec · {night} · Saved figures and measurements</footer></main>
<dialog aria-label="Enlarged figure"><button type="button">Close</button><img alt=""></dialog><script>{SCRIPT}</script></body></html>'''
    destination = root/'index.html'
    temporary = destination.with_suffix('.html.tmp')
    temporary.write_text(html);temporary.replace(destination)
    return {'path':str(destination), 'revision':revision.name, 'embedded_figures':page.images,
            'warnings':page.warnings, 'bytes':destination.stat().st_size}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Rebuild one portable epoch report from saved results')
    parser.add_argument('night')
    parser.add_argument('--project-root', default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args(argv)
    print(json.dumps(build_epoch_page(args.night, args.project_root), indent=2))


if __name__ == '__main__':
    main()
