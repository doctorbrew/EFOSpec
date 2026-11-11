"""Reviewed typing annotations; never invokes reduction or classification."""
from copy import deepcopy
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from .desktop_session import resolve_session
from .inventory import sha256

SCHEMA = 'efospec-typing-metadata/1'
KINDS = ('host_catalogue', 'narrow_lines', 'transient_spectral')
STATUSES = ('unreviewed', 'candidate', 'accepted', 'rejected')
IDENTITY = ('object_id', 'path', 'source_sha256')


def read(path):
    return json.loads(Path(path).read_text())


def skeleton(path):
    session = resolve_session(path)
    run = session.run
    manifest = session.manifest
    night = manifest.get('night', session.night)
    date.fromisoformat(night)
    spectra = []
    for item in manifest['results']:
        if item.get('role') != 'science':
            continue
        product = Path(item['product'])
        product = (run / product).resolve()
        source = product.with_suffix('.asci')
        if not source.is_relative_to(run) or not source.is_file():
            raise ValueError('Science ASCII spectrum missing or outside selected reduction')
        if not str(item.get('object', '')).strip():
            raise ValueError('Science spectrum has no object identity')
        spectra.append(dict(object_id=item['object'], path=source.relative_to(run).as_posix(),
                            source_sha256=sha256(source), host_status='unreviewed',
                            redshift_status='unreviewed', host_candidates=[],
                            provenance=[dict(kind='efospec_reduction', manifest=str(run/'run.json'),
                                             raw=item.get('raw'), raw_sha256=item.get('raw_sha256'),
                                             date_obs=item.get('date_obs'))]))
        # Only a recorded product URL is propagated; never manufacture an archive URL.
        if item.get('spectrum_url'):
            spectra[-1]['spectrum_url'] = item['spectrum_url']
    return dict(schema=SCHEMA, night=night, reduction_manifest_path=str(run/'run.json'),
                reduction_manifest_sha256=sha256(run/'run.json'), spectra=spectra)


def _number(record, key):
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise ValueError(f'{key} must be a finite nonnegative number or null')
    return value


def _text(record, key):
    if not isinstance(record, dict) or not isinstance(record.get(key), str) or not record[key].strip():
        raise ValueError(f'{key} is required')


def validate(path, document):
    """Bind every record to the selected manifest, product and exact identity."""
    if not isinstance(document, dict):
        raise ValueError('Typing metadata must be a JSON object')
    expected = skeleton(path)
    for key in ('schema', 'night', 'reduction_manifest_sha256', 'reduction_manifest_path'):
        if document.get(key) != expected[key]:
            raise ValueError('Typing metadata belongs to a different reduction revision: '+key)
    by_path = {r['path']: r for r in expected['spectra']}
    records = document.get('spectra')
    if not isinstance(records, list) or len(records) != len(by_path):
        raise ValueError('Typing metadata must contain each selected science spectrum exactly once')
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Each spectrum record must be a JSON object')
        source = record.get('path')
        if not isinstance(source, str) or source in seen or source not in by_path:
            raise ValueError('Repeated or unknown typing spectrum')
        seen.add(source)
        if any(record.get(k) != by_path[source][k] for k in IDENTITY):
            raise ValueError('Typing metadata spectrum hash/path/object identity mismatch')
        for key in ('host_status', 'redshift_status'):
            if record.get(key) not in STATUSES:
                raise ValueError('Invalid '+key)
        for key in ('host_redshift', 'host_redshift_uncertainty', 'host_separation_arcsec',
                    'adopted_redshift', 'adopted_redshift_uncertainty'):
            _number(record, key)
        if not isinstance(record.get('host_candidates'), list) or not all(isinstance(c, dict) for c in record['host_candidates']):
            raise ValueError('host_candidates must be a list of full catalogue records')
        if not isinstance(record.get('provenance'), list):
            raise ValueError('provenance must be a list')
        if record.get('host_status') == 'accepted':
            for key in ('host_name', 'host_source'):
                _text(record, key)
        adopted = record.get('adopted_redshift')
        if adopted is not None:
            if record['redshift_status'] != 'accepted' or record.get('adopted_redshift_kind') not in KINDS:
                raise ValueError('Adopted redshift requires explicit acceptance and a supported kind')
            _text(record, 'adopted_redshift_source')
            if record['adopted_redshift_kind'] == 'host_catalogue' and (
                    record['host_status'] != 'accepted' or record.get('host_redshift') != adopted):
                raise ValueError('Host adoption requires an accepted host and identical host/adopted z')
        elif record['redshift_status'] == 'accepted':
            raise ValueError('Accepted redshift requires an adopted value')
        for status, key in (('host_status', 'host_review'), ('redshift_status', 'redshift_review')):
            if record[status] == 'accepted':
                review = record.get(key, {})
                _text(review, 'reviewer'); _text(review, 'reviewed_at')
                stamp = datetime.fromisoformat(review['reviewed_at'].replace('Z', '+00:00'))
                if stamp.utcoffset() is None:
                    raise ValueError('Review time must include its timezone')
        url = record.get('spectrum_url')
        if url:
            _text(record, 'spectrum_url')
            parts = urlsplit(url)
            if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password:
                raise ValueError('spectrum_url must be a real public HTTP(S) product URL')
    # Disallow NaN anywhere, including retained catalogue data.
    json.dumps(document, allow_nan=False)
    return document


def load(path):
    run = resolve_session(path).run
    target = run/'typing-metadata.json'
    return validate(run, read(target)) if target.exists() else None


def save(path, document, reviewer, *, accept_hosts=(), accept_redshifts=(), expected_revision=None):
    """Append an immutable snapshot and atomically replace the current export.

    Acceptance must be supplied for changed accepted fields, not inferred from a
    JSON status. Optimistic revision checks and a single-writer lock prevent lost edits.
    """
    run = resolve_session(path).run
    target = run/'typing-metadata.json'
    lock = run/'.typing-metadata.lock'
    _text({'reviewer': reviewer}, 'reviewer')
    with lock.open('x'):
        try:
            previous = load(run)
            if (previous or {}).get('revision_id') != expected_revision:
                raise ValueError('Typing metadata changed while editing; reload before saving')
            doc = deepcopy(document)
            now = datetime.now(timezone.utc).isoformat()
            review = dict(reviewer=reviewer.strip(), reviewed_at=now)
            old = {r['path']: r for r in (previous or {}).get('spectra', [])}
            paths = {r['path'] for r in doc['spectra']}
            if (set(accept_hosts) | set(accept_redshifts)) - paths:
                raise ValueError('Acceptance refers to an unknown spectrum')
            for record in doc['spectra']:
                prior = old.get(record['path'], {})
                for prefix, status, review_key, accepted in (
                    ('host_', 'host_status', 'host_review', accept_hosts),
                    ('adopted_redshift', 'redshift_status', 'redshift_review', accept_redshifts)):
                    keys = {k for k in record.keys() | prior.keys() if k.startswith(prefix)} - {review_key}
                    changed = any(record.get(k) != prior.get(k) for k in keys) or record.get(status) != prior.get(status)
                    if record['path'] in accepted:
                        record[status] = 'accepted'
                        record[review_key] = review
                    elif record.get(status) == 'accepted':
                        if changed or prior.get(status) != 'accepted':
                            raise ValueError('Explicit acceptance required for changed '+status)
                        record[review_key] = prior[review_key]
                    elif changed:
                        record[review_key] = review
                if record != prior:
                    record['review'] = review
            doc.update(revision_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid4().hex[:8],
                       previous_revision_id=(previous or {}).get('revision_id'), review=review)
            validate(run, doc)
            history = run/'typing-metadata-revisions'
            history.mkdir(exist_ok=True)
            # Preserve an imported pre-existing export as well as every new revision.
            if previous:
                prior_path = history/('import-'+sha256(target)+'.json')
                if not prior_path.exists():
                    prior_path.write_bytes(target.read_bytes())
            payload = json.dumps(doc, indent=2, ensure_ascii=False, allow_nan=False)+'\n'
            snapshot = history/(doc['revision_id']+'.json')
            with snapshot.open('x') as stream:
                stream.write(payload)
            temporary = run/('.typing-metadata-'+uuid4().hex+'.tmp')
            try:
                temporary.write_text(payload)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            return doc
        finally:
            lock.unlink(missing_ok=True)


def add_arguments(parser):
    parser.add_argument('action', choices=('show', 'init', 'edit', 'report'))
    parser.add_argument('path', help='Night folder, reduction folder or run.json')
    parser.add_argument('--reviewer', help='Required identity for a saved metadata revision')
    parser.add_argument('--evidence', help='Import saved redshifts.json; requires this exact parent reduction')
    parser.add_argument('--input', help='Edited full metadata JSON; original binding/revision required')
    parser.add_argument('--spectrum', help='Exact ASCII filename or products/path to edit')
    parser.add_argument('--set', action='append', default=[], metavar='FIELD=VALUE', help='JSON value, or plain text; null clears an optional value')
    parser.add_argument('--candidates', help='JSON list of catalogue candidates, retained without selecting a host')
    parser.add_argument('--accept-host', action='store_true')
    parser.add_argument('--accept-redshift', action='store_true')


def command(args):
    if args.action == 'report':
        return refresh_report(args.path)
    current = load(args.path)
    if args.action == 'show':
        return current or skeleton(args.path)
    if args.action == 'init' and current:
        raise ValueError('Metadata already exists; use edit')
    if args.action == 'init' and (args.input or args.evidence or args.set or args.candidates or args.accept_host or args.accept_redshift):
        raise ValueError('init creates unreviewed records; use edit for annotations')
    doc = read(args.input) if args.input else deepcopy(current or skeleton(args.path))
    if args.evidence:
        doc = import_evidence(args.path, doc, args.evidence)
    hosts = []; redshifts = []
    if args.set or args.candidates or args.accept_host or args.accept_redshift:
        matches = [r for r in doc['spectra'] if args.spectrum in (r['path'], Path(r['path']).name)]
        if len(matches) != 1:
            raise ValueError('Select one exact --spectrum to edit or accept')
        record = matches[0]
        for assignment in args.set:
            key, sep, value = assignment.partition('=')
            if not sep or key in IDENTITY or key in ('host_review', 'redshift_review', 'review'):
                raise ValueError('Invalid or protected metadata field: '+key)
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
            record[key] = value
        if args.candidates:
            record['host_candidates'] = read(args.candidates)
        if args.accept_host: hosts.append(record['path'])
        if args.accept_redshift: redshifts.append(record['path'])
    return save(args.path, doc, args.reviewer, accept_hosts=hosts, accept_redshifts=redshifts,
                expected_revision=doc.get('revision_id'))


def import_evidence(path, document, evidence_path):
    """Import saved line/catalogue evidence only from this reduction revision.

    Copy all candidates and the full measurement record, never its nearest-host
    suggestion into accepted fields. No query, fit or classification is run.
    """
    run = resolve_session(path).run
    validate(run, document)
    evidence_path = Path(evidence_path).resolve()
    evidence = read(evidence_path)
    parents = evidence.get('parent_run_sha256', {})
    if (evidence.get('night') != document['night'] or
            parents.get(str(run/'run.json')) != document['reduction_manifest_sha256']):
        raise ValueError('Host evidence belongs to an older or different reduction revision')
    doc = deepcopy(document)
    by_product = {(run/r['path']).with_suffix('.fits').resolve():r for r in doc['spectra']}
    for entry in evidence['results']:
        record_path = Path(entry['path'])
        if sha256(record_path) != entry['sha256']:
            raise ValueError('Host evidence record changed')
        record = read(record_path)
        product = Path(record['product']).resolve()
        if product not in by_product:
            continue
        target = by_product[product]
        if record['object'] != target['object_id']:
            raise ValueError('Host evidence object identity mismatch')
        for key in ('product', 'raw', 'images', 'diagnostic_arrays'):
            if sha256(Path(record[key])) != record[key+'_sha256']:
                raise ValueError('Host evidence input changed: '+key)
        ned = record['ned']
        if sha256(Path(ned['query_file'])) != ned['query_sha256']:
            raise ValueError('Host evidence catalogue query changed')
        for candidate in ned.get('candidates', []):
            if candidate not in target['host_candidates']:
                target['host_candidates'].append(deepcopy(candidate))
        target['provenance'].append(dict(evidence_path=str(evidence_path), evidence_sha256=sha256(evidence_path),
                                         record_path=str(record_path), record_sha256=entry['sha256'], record=record))
    return doc


def refresh_report(path):
    """Refresh only the selected night's saved-data HTML, never its pipeline."""
    run = resolve_session(path).run
    if run.name != 'reduction' or run.parent.parent.name != 'nightly':
        raise ValueError('Nightly HTML refresh requires a dated nightly reduction')
    root = run.parent.parent.parent
    if resolve_session(root).run != run:
        raise ValueError('Cannot publish metadata from an older reduction revision')
    from .epoch_report import build_epoch_page
    return build_epoch_page(root.name, root.parent.parent)
