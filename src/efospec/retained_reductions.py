"""Display unchanged products from earlier revisions of the same observing night."""
from pathlib import Path
import json

from .inventory import sha256

GROUPS = ('results', 'review_counts', 'errors', 'skipped')


def raw_key(row):
    return row.get('raw', row.get('path', ''))


def attempted(run):
    return {raw_key(row) for group in (*GROUPS, 'counts', 'exposure_states')
            for row in run.get(group, []) if raw_key(row)}


def product_paths(folder, row, group):
    product = (folder/'products'/Path(row['product']).name if group == 'results'
               else Path(row['product']))
    return [product, Path(row.get('ascii', product.with_suffix('.asci')))]


def saved_groups(page, revision, run):
    """Prefer the last displayed selection, including explicitly adopted recoveries."""
    snapshot = page.read(revision/'report-products.json')
    if snapshot:
        if snapshot.get('parent_sha256') != sha256(revision/'reduction/run.json'):
            raise ValueError('saved report selection parent changed')
        groups = []
        for entry in snapshot['groups']:
            folder = (page.root/entry['folder']).resolve()
            folder.relative_to(page.root)
            if sha256(folder/'run.json') != entry['manifest_sha256']:
                raise ValueError('saved report selection manifest changed')
            manifest = page.read(folder/'run.json')
            selected = dict(manifest, **{key: [r for r in manifest.get(key, [])
                if raw_key(r) in entry.get(key, [])] for key in GROUPS})
            groups.append((folder, selected, entry.get('product_sha256', {})))
        return groups
    from .manual_recovery_report import selected_manual_recoveries
    # Manual selections supersede their parent products.
    groups = [(folder, manifest, {}) for folder, manifest in
              reversed(selected_manual_recoveries(revision/'reduction'))]
    pointer = page.read(page.root/'rescue/current.json')
    if pointer.get('night') == page.night:
        folder = (page.root/pointer['path']).resolve()
        folder.relative_to(page.root/'rescue')
        manifest = page.read(folder/'run.json')
        if manifest.get('parent_sha256') == sha256(revision/'reduction/run.json'):
            if sha256(folder/'run.json') != pointer['run_sha256']:
                raise ValueError('saved rescue manifest changed')
            groups.append((folder, manifest, {}))
    groups.append((revision/'reduction', run, {}))
    return groups


def retained_reductions(page, revision, run):
    """Newest attempt wins; never substitute an older success for a newer failure."""
    frames = {f['path']: f for f in page.read(revision/'observing-log.json').get('frames', [])}
    blocked = attempted(run)
    targets = page.read(revision/'night.json').get('targets') or []
    blocked.update(raw for raw, f in frames.items() if f.get('metadata', {}).get('OBJECT') in targets)
    retained = []
    # Revision names have a UTC timestamp prefix; historical views exclude later runs.
    for previous in sorted((page.root/'nightly').iterdir(), reverse=True):
        if not previous.is_dir() or previous.name >= revision.name:
            continue
        state = page.read(previous/'night.json')
        manifest = page.read(previous/'reduction/run.json')
        if state.get('night') != page.night or not manifest:
            continue
        if manifest.get('execution_status') == 'running' or state.get('status') == 'running':
            continue
        old_frames = {f['path']: f for f in page.read(previous/'observing-log.json').get('frames', [])}
        try:
            sources = saved_groups(page, previous, manifest)
        except (OSError, ValueError, KeyError) as error:
            page.warnings.append(f'{previous.name}: {error}')
            blocked.update(attempted(manifest))
            continue
        for folder, source, hashes in sources:
            available = attempted(source) - blocked
            selected = dict(source, **{key: [] for key in GROUPS})
            plots = [page.read(p) for p in (folder/'style-preview').glob('FitSpectrum_*.json')]
            for group in GROUPS:
                for row in source.get(group, []):
                    raw = raw_key(row)
                    if raw not in available or raw not in frames:
                        continue
                    current, old = frames[raw], old_frames.get(raw, {})
                    digest = row.get('raw_sha256', old.get('sha256'))
                    if (not digest or digest != current.get('sha256') or
                            current.get('setup') != old.get('setup') or
                            current.get('metadata', {}).get('OBJECT') != old.get('metadata', {}).get('OBJECT')):
                        page.warnings.append(f'{Path(raw).name}: earlier result does not match current raw record')
                        continue
                    try:
                        if Path(raw).is_file() and sha256(Path(raw)) != digest:
                            raise ValueError('raw file changed')
                        if group in ('results', 'review_counts'):
                            bindings = dict(hashes)
                            for plot in plots:
                                bindings.update(plot.get('input_sha256', {}))
                            bindings.update(row.get('product_sha256', {}))
                            product, ascii_path = product_paths(folder, row, group)
                            product.resolve().relative_to(page.root)
                            expected = bindings.get(str(product))
                            if not expected or sha256(product) != expected:
                                raise ValueError('saved FITS missing, changed or lacks a recorded checksum')
                            for path, expected in row.get('product_sha256', {}).items():
                                Path(path).resolve().relative_to(page.root)
                                if sha256(Path(path)) != expected:
                                    raise ValueError('saved product dependency changed')
                            if ascii_path.is_file():
                                ascii_path.resolve().relative_to(page.root)
                                if str(ascii_path) in bindings and sha256(ascii_path) != bindings[str(ascii_path)]:
                                    raise ValueError('saved ASCII changed')
                        selected[group].append(row)
                    except (OSError, ValueError) as error:
                        page.warnings.append(f'{Path(raw).name}: earlier result withheld: {error}')
            if any(selected[key] for key in GROUPS):
                retained.append((folder, selected))
            blocked.update(attempted(source))
        blocked.update(attempted(manifest))
    return retained


def save_report_products(page, revision, groups):
    """Remember displayed products so later target-only reports retain selected rescues."""
    if not (revision/'reduction/run.json').is_file():
        return  # A log-only invocation has no reduction selection to persist yet.
    entries = []
    for folder, manifest in groups:
        entry = dict(folder=str(folder.relative_to(page.root)),
                     manifest_sha256=sha256(folder/'run.json'), product_sha256={})
        for key in GROUPS:
            entry[key] = [raw_key(row) for row in manifest.get(key, [])]
        for key in ('results', 'review_counts'):
            for row in manifest.get(key, []):
                for path in product_paths(folder, row, key):
                    path.resolve().relative_to(page.root)
                    if path.is_file():
                        entry['product_sha256'][str(path)] = sha256(path)
        entries.append(entry)
    payload = dict(parent_sha256=sha256(revision/'reduction/run.json'), groups=entries)
    (revision/'report-products.json').write_text(json.dumps(payload, indent=2)+'\n')
