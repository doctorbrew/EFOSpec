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
from .report import CSS


def _text(value):
    return escape(str(value))


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

    def figure(self, path, title):
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
        return (f'<figure class="plot"><figcaption>{_text(title)}</figcaption>'
                f'<button class="enlarge" type="button" aria-label="Enlarge {_text(title)}">'
                f'<img loading="lazy" src="{url}" alt="{_text(title)}"></button></figure>')

    def spectra(self, run_dir, run):
        records = [self.read(p) for p in sorted((run_dir/'style-preview').glob('FitSpectrum_*.json'))]
        sections = []
        for i, result in enumerate(run.get('results', [])):
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
            sections.append(f'<article class="exposure" id="spectrum-{i}"><h3>{_text(title)}</h3>'
                f'<p class="caption">{_text(result.get("date_obs", ""))} UTC{identity} · {downloads}</p>'
                f'<div class="plots">{"".join(cards)}</div></article>')
        return ''.join(sections) or '<p>No spectra recorded in this revision.</p>'

    def observations(self, revision, run):
        outcomes = {}
        for group, label in [('results', 'Spectrum'), ('errors', 'Failed'), ('skipped', 'Unsupported')]:
            for i, result in enumerate(run.get(group, [])):
                raw = Path(result.get('raw', result.get('path', ''))).name
                reason = {'sky_flexure_unreliable':'Sky-line check', 'source_selection_required':'Choose source',
                          'unsupported_setup':'Unsupported setup'}.get(result.get('code'), label)
                outcomes[raw] = f'<a href="#spectrum-{i}">Spectrum ↓</a>' if group == 'results' else _text(reason)
        rows = []
        for frame in self.read(revision/'observing-log.json').get('frames', []):
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
                outcomes.get(raw, 'Not reduced')])
        return _table(['Target', 'UTC start', 'Role', 'Setup', 'Slit', 'Seconds', 'Result'], rows)

    def problems(self, run):
        groups = {}
        for item in run.get('errors', [])+run.get('skipped', []):
            code = item.get('code', 'unknown')
            groups.setdefault(code, []).append(item)
        rows = []
        for code, items in groups.items():
            names = Counter(x.get('object', 'Unknown') for x in items)
            targets = ', '.join(k+(f' ×{v}' if v > 1 else '') for k, v in names.items())
            detail = {'sky_flexure_unreliable':'Sky lines did not pass the flexure checks.',
                'source_selection_required':'Multiple traces; target selection needs review.',
                'unsupported_setup':'This archive reduction does not support the recorded setup.'}.get(code, items[0].get('reason', items[0].get('error', code)))
            rows.append([_text(code), len(items), _text(targets), _text(detail)])
        return _table(['Issue', 'Exposures', 'Targets', 'Meaning'], rows) if rows else '<p>No recorded reduction failures.</p>'

    def qc(self, revision, run):
        packets = {}
        # Current QC wins; retained original packets supply reviewed experiments.
        for folder in [self.root/'QC', revision/'QC']:
            for path in sorted(folder.glob('*/review.json')):
                review = self.read(path)
                if review.get('raw_name'):
                    packets[review['raw_name']] = (path.parent, review)
        current = {Path(e.get('path', '')).name for e in run.get('errors', [])}
        sections, backgrounds = [], []
        for raw, (folder, review) in packets.items():
            if raw not in current:
                continue
            title = review.get('object', raw)
            original = self.root/'QC'/Path(raw).stem
            cards = []
            for suffix, label in [('science', 'Detector and candidates'), ('traces', 'Traces and profiles'),
                                  ('acquisition-1', 'Acquisition 1'), ('acquisition-2', 'Acquisition 2')]:
                matches = sorted(folder.glob(f'FitQC_*_{suffix}.jpg'))
                if matches:
                    cards.append(self.figure(matches[0], title+' / '+label))
            candidates = ', '.join(f'C{c.get("number", i+1)}: x={c.get("anchor_raw_x", c.get("raw_spatial_pixel", 0)):.2f}'
                                   for i, c in enumerate(review.get('candidates', [])))
            sections.append(f'<article class="exposure"><h3>{_text(title)}</h3>'
                f'<p class="caption">{_text(raw)} · Identity {_text(review.get("identity", "unverified").lower())}</p>'
                f'<p>{_text(candidates)} <span class="caption">(raw detector pixels)</span></p>'
                f'<div class="qc-plots">{"".join(cards)}</div></article>')
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
                ''.join(backgrounds) or '<p>No retained polynomial background experiments for these exposures.</p>')

    def calibrations(self):
        rows, seen = [], set()
        for path in sorted((self.root/'calibrations').glob('*/run.json')):
            for group in self.read(path).get('groups', []):
                if group['id'] in seen:
                    continue
                seen.add(group['id']);s = group.get('setup', {})
                wave = group.get('wave_qa', [])
                rms = ', '.join(f'{w["held_out_rms_pixel"]:.3f}' for w in wave if 'held_out_rms_pixel' in w)
                rows.append([_text(s.get('grism', '')), _text(s.get('filter', '')), _text(s.get('slit', '')),
                             _text(group.get('status', 'unknown').replace('_', ' ')), rms or '—'])
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
    records = _table(['Stage', 'Status', 'Error'], stage_rows)
    records += '<details><summary>Download logs and provenance</summary><ul>'+''.join('<li>'+d+'</li>' for d in downloads if d)+'</ul></details>'
    records += _table(['Folder', 'Contents'], [['nightly/', 'Current and previous processing revisions'],
        ['QC/', 'Retained source and background experiments'], ['calibrations/', 'Native masters and group selections'],
        ['archive/', 'Earlier reductions, diagnostics and logs']])
    content = [page.observations(revision, run), page.spectra(revision/'reduction', run), page.problems(run), qc,
               background, page.calibrations(), page.archive(revision), records]
    sections = ''.join(f'<section class="target" id="{anchor}"><h2>{title}</h2>{body}</section>'
                       for (anchor, title), body in zip(titles, content))
    stats = ' · '.join(f'{len(run.get(k, []))} {label}' for k, label in [('results','spectra'), ('errors','failed'), ('skipped','unsupported')])
    extra_css = """
    main{max-width:1480px}.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.tabs a{padding:7px 12px;border:1px solid var(--line);border-radius:5px;text-decoration:none;background:var(--panel)}
    .target>h2{margin-bottom:18px}.exposure{margin:24px 0 32px}.qc-plots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
    .enlarge{display:block;padding:0;border:0;background:transparent;width:100%;cursor:zoom-in}.enlarge:focus-visible{outline:3px solid var(--forest)}
    .plots .plot-image{aspect-ratio:auto}td{white-space:normal}dialog{max-width:95vw;max-height:95vh;padding:10px;border:1px solid var(--line);border-radius:8px}dialog img{display:block;max-width:100%;height:auto}dialog button{position:sticky;top:0;padding:10px 18px;cursor:pointer}dialog::backdrop{background:#172c43bb}
    @media(max-width:800px){.plots{grid-template-columns:1fr;overflow:visible}.qc-plots{grid-template-columns:1fr}.plot{min-width:0}h1{font-size:30px}.intro{display:block}}
    """
    warning = '<p class="note">'+_text('; '.join(page.warnings))+'</p>' if page.warnings else ''
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fieldnotes · {night} · EFOSpec</title><style>{CSS}{extra_css}</style></head><body><main>
<header class="masthead"><span class="brand">Fieldnotes. / EFOSpec</span><span class="eyebrow">EFOSC2 · {night}</span></header>
<div class="intro"><div><span class="eyebrow">Observing night</span><h1>{night}</h1></div><p>{stats}</p></div>
<p class="caption">Archive-calibration reduction · {_text(state.get('status', 'unknown'))} · revision {_text(revision.name)}</p>
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
