"""Compact acquisition annotations and read-only host verification from saved JSON."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from urllib.parse import urlsplit
from .typing_metadata import load


def records_for_run(run):
    document = load(run)
    return {r['path']: r for r in document['spectra']} if document else {}


def review_anchor(record):
    return 'host-review-'+sha256(record['path'].encode()).hexdigest()[:12]


def _z(value, uncertainty=None):
    result = f'{value:.6g}'
    if uncertainty is not None:
        result += f' ± {uncertainty:.3g}'
    return result


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
    if host and record.get('host_redshift') is not None:
        method = record.get('host_redshift_method') or 'method unknown'
        chips.append('Catalogue z: '+_z(record['host_redshift'],record.get('host_redshift_uncertainty'))+' ('+method+')')
    if record.get('redshift_status') == 'accepted' and record.get('adopted_redshift') is not None:
        chips.append('Adopted z: '+_z(record['adopted_redshift'],record.get('adopted_redshift_uncertainty'))+
                     ' · '+record['adopted_redshift_kind'].replace('_',' '))
    else:
        for candidate in record.get('redshift_candidates', []):
            if candidate.get('preferred') and candidate.get('redshift') is not None:
                chips.append('Published z: '+_z(candidate['redshift'],candidate.get('uncertainty'))+
                             ' · '+candidate['kind'].replace('_',' ')+' (not adopted)')
    if not chips:
        return ''
    review_link = ('<a class="host-tag" href="#'+review_anchor(record)+'">'
                   +('Review evidence' if accepted else 'Verify cross-match')+'</a>') if link_to_review else ''
    return ('<div class="host-tags" aria-label="Host cross-match">'
            +''.join('<span class="host-tag">'+escape(text)+'</span>' for text in chips)
            +review_link+'</div>')


def acquisition_metadata(page, object_id):
    return ''.join(spectrum_metadata(page,r) for r in getattr(page,'typing_annotations',{}).values()
                   if r['object_id'] == object_id)


def _link(url, label):
    # Metadata is editable: never put a javascript/data/file URL into an external button.
    if not isinstance(url, str):
        return ''
    parsed = urlsplit(url)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        return ''
    return '<a class="host-link" href="'+escape(url,quote=True)+'" target="_blank" rel="noopener noreferrer">'+escape(label)+'</a>'


def verification_section(page):
    records = list(getattr(page,'typing_annotations',{}).values())
    if not records:
        return ''
    from .naming import source_order
    content = ('<p>Check the proposed association against the acquisition image and catalogue records. '
               'Catalogue, narrow-line and transient-template redshifts remain separate. '
               'Accept changes in the desktop Host &amp; redshift tab; these proposals are not typing inputs.</p>')
    for record in sorted(records,key=lambda r:source_order({'object':r['object_id']})):
        content += '<article class="exposure" id="'+review_anchor(record)+'"><h3>'+escape(record['object_id'])+'</h3>'
        tags = spectrum_metadata(page,record,link_to_review=False)
        content += tags or '<p>No proposed cross-match recorded.</p>'
        preferred = record.get('preferred_crossmatch', {})
        if preferred.get('name') and record.get('host_name') and preferred['name'] != record['host_name']:
            content += '<p class="caption">Original catalogue proposal: '+escape(preferred['name'])+'</p>'
        if preferred.get('rationale'):
            content += '<p>'+escape(preferred['rationale'])+'</p>'
        if preferred.get('caveat'):
            content += '<p class="note">'+escape(preferred['caveat'])+'</p>'
        links = [_link(v.get('url'),v.get('label','Reference')) for v in record.get('verification_links',[])]
        if (record.get('host_source','').startswith(('https://','http://'))
                and record['host_source'] not in {v.get('url') for v in record.get('verification_links',[])}):
            links.insert(0,_link(record['host_source'],'NED host record'))
        if record.get('spectrum_url'):
            links.append(_link(record['spectrum_url'],'Original spectrum'))
        content += '<div class="host-links">'+''.join(dict.fromkeys(filter(None,links)))+'</div>'
        candidates = record.get('host_candidates',[])
        if candidates:
            from .epoch_report import _table
            rows=[]
            for candidate in candidates:
                m=candidate.get('metadata',{});z=m.get('z',candidate.get('redshift'))
                method=candidate.get('redshift_method') or {'S':'spectroscopic','P':'photometric'}.get(str(m.get('zflag',''))[:1],'unknown')
                sep=candidate.get('separation_arcsec')
                rows.append([escape(str(candidate.get('name',''))),escape(str(candidate.get('catalogue',''))),
                             f'{sep:.2f}' if sep is not None else '—',_z(z) if z is not None else '—',escape(method)])
            content += '<details><summary>Catalogue candidates ('+str(len(candidates))+')</summary>'
            content += _table(['Name','Catalogue','Offset (arcsec)','z','Method'],rows)+'</details>'
        # Keep full identity/time/uncertainty provenance without cluttering the acquisition tags.
        content += '<details><summary>Metadata and review history</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'
        content += escape(json.dumps(record,indent=2,ensure_ascii=False))+'</pre></details></article>'
    content += '<p>'+page.download(page.typing_run/'typing-metadata.json','Typing metadata JSON')+'</p>'
    return content


HOST_CSS = '''
.host-tags,.host-links{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 18px}
.host-tag{font-size:13px;padding:5px 10px;border:1px solid #dfe2d7;border-radius:5px;background:#eef0e8;overflow-wrap:anywhere}
.host-link{display:inline-block;border:1px solid #244d3d;border-radius:5px;padding:7px 13px;font-size:13px}
.host-link:focus-visible,.host-tag:focus-visible{outline:2px solid #244d3d;outline-offset:3px}
'''
