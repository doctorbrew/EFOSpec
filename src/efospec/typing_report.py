"""Compact acquisition annotations and read-only host verification from saved JSON."""
from hashlib import sha256
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from .typing_metadata import load


def records_for_run(run):
    document = load(run)
    return {r['path']: r for r in document['spectra']} if document else {}


def review_anchor(record):
    return 'host-review-'+sha256(record['path'].encode()).hexdigest()[:12]


def spectrum_metadata(page, record, *, link_to_review=True):
    """Compatibility name: rendered only below acquisition figures, never spectra."""
    chips = []
    preferred = record.get('preferred_crossmatch', {})
    host = record.get('host_name')
    accepted = record.get('host_status') == 'accepted'
    if host:
        prefix = 'Host: ' if accepted else 'Rejected host: ' if record.get('host_status') == 'rejected' else 'Proposed host: '
        chips.append(prefix+host)
        separation = record.get('host_separation_arcsec')
    elif preferred:
        chips.append('Positional counterpart: '+preferred['name'])
        separation = preferred.get('separation_arcsec')
    else:
        separation = None
    if separation is not None:
        chips.append(f'Offset: {separation:.2f} arcsec')
    if not chips:
        return ''
    review_link = ('<a class="host-tag" href="#'+review_anchor(record)+'">'
                   +('Review evidence' if accepted else 'Verify cross-match')+'</a>') if link_to_review else ''
    return ('<div class="host-tags" aria-label="Host cross-match">'
            +''.join('<span class="host-tag">'+escape(text)+'</span>' for text in chips)
            +review_link+'</div>')


def acquisition_metadata(page, object_id, *, show_candidates=False):
    """Render association evidence once, beside the object's acquisition images."""
    rendered = getattr(page, 'rendered_host_records', set())
    page.rendered_host_records = rendered
    content = ''
    for record in getattr(page,'typing_annotations',{}).values():
        if record['object_id'] != object_id or record['path'] in rendered:continue
        rendered.add(record['path'])
        content += '<div id="'+review_anchor(record)+'">'+verification_details(page,record,show_candidates=show_candidates)+'</div>'
    return content


def record_raw(record):
    return next((Path(p['raw']).name for p in record.get('provenance',[])
                 if p.get('kind')=='efospec_reduction' and p.get('raw')), None)


def catalogue_redshift(candidate):
    from .field_catalogues import redshift_label
    if 'metadata' in candidate:return redshift_label(candidate)
    value=candidate.get('redshift')
    if value is None:return '— no catalogued redshift'
    method=candidate.get('redshift_method') or candidate.get('method') or 'method unknown'
    return f'z={value:.6g} ({method})'


def ned_cell(record):
    """Only a NED catalogue measurement can populate z (NED)."""
    name=record.get('host_name') or record.get('preferred_crossmatch',{}).get('name')
    candidates=record.get('host_candidates',[])+record.get('catalogue_sources',[])
    candidate=next((c for c in candidates if c.get('catalogue')=='NED' and c.get('name')==name),None)
    if candidate is None:return None
    return escape(catalogue_redshift(candidate)+'; '+name+'; candidate association')


def emission_cell(page, record, candidate_name):
    """Do not assign the target's line system to every positional neighbour."""
    if record.get('host_name')!=candidate_name or record.get('host_status')=='rejected':return 'Not associated'
    raw=record_raw(record)
    from .redshift_report import redshift_cells
    measurement=getattr(page,'redshift_records',{}).get(raw)
    cell=redshift_cells(measurement,previous_revision=raw in getattr(page,'previous_redshift_raws',set()))[1]
    if measurement and measurement.get('spectral',{}).get('z_heliocentric') is not None:
        cell+=' · candidate association'
    return cell


def _link(url, label):
    # Metadata is editable: never put a javascript/data/file URL into an external button.
    if not isinstance(url, str) or 'astronote' in url.casefold() or 'astronote' in label.casefold():
        return ''
    parsed = urlsplit(url)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        return ''
    return '<a class="host-link" href="'+escape(url,quote=True)+'" target="_blank" rel="noopener noreferrer">'+escape(label)+'</a>'


def verification_details(page, record, *, show_candidates=False):
    content = spectrum_metadata(page,record,link_to_review=False)
    preferred = record.get('preferred_crossmatch', {})
    # Use catalogue facts, not the old assessment's AstroNote/TNS comparisons.
    if preferred.get('catalogue') and preferred.get('name'):
        content += '<p>'+escape(preferred['catalogue']+' positional candidate: '+preferred['name'])
        if preferred.get('separation_arcsec') is not None:
            content += f" ({preferred['separation_arcsec']:.2f} arcsec from the observing-block target)"
        content += ('. Association accepted by the operator.</p>' if record.get('host_status')=='accepted'
                    else '. The association is unconfirmed.</p>')
    links = [_link(v.get('url'),v.get('label','Reference')) for v in record.get('verification_links',[])]
    if record.get('host_source'):
        links.insert(0,_link(record['host_source'],'Host catalogue record'))
    content += '<div class="host-links">'+''.join(dict.fromkeys(filter(None,links)))+'</div>'
    if show_candidates and record.get('host_candidates'):
        from .epoch_report import _table
        rows=[]
        for candidate in record['host_candidates']:
            sep=candidate.get('separation_arcsec')
            rows.append([escape(candidate.get('name','')),escape(candidate.get('catalogue','')),
                         f'{sep:.2f}' if sep is not None else '—',
                         escape(catalogue_redshift(candidate)) if candidate.get('catalogue')=='NED' else '—',
                         emission_cell(page,record,candidate.get('name'))])
        content += _table(['Galaxy candidate','Catalogue','Offset (arcsec)','z (NED)','z (Host Emission)'],rows)
    return content


def verification_section(page):
    """Compatibility renderer for saved annotations without acquisition imagery."""
    return ''.join(acquisition_metadata(page,r['object_id'],show_candidates=True)
                   for r in getattr(page,'typing_annotations',{}).values())


HOST_CSS = '''
.host-tags,.host-links{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 18px}
.host-tag{font-size:13px;padding:5px 10px;border:1px solid #dfe2d7;border-radius:5px;background:#eef0e8;overflow-wrap:anywhere}
.host-link{display:inline-block;border:1px solid #244d3d;border-radius:5px;padding:7px 13px;font-size:13px}
.host-link:focus-visible,.host-tag:focus-visible{outline:2px solid #244d3d;outline-offset:3px}
'''
