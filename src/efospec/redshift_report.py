"""Read-only, hash-checked redshift evidence for the dated observing log."""
from html import escape
from pathlib import Path
import math
from .inventory import sha256
from .field_catalogues import redshift_label


def load_redshifts(page, parent, rescue=None):
    path=page.root/'QC/redshift-current.json'
    if not path.exists():return {}
    pointer=page.read(path);manifest_path=(page.root/pointer['path']).resolve()
    if not manifest_path.is_relative_to(page.root/'QC') or pointer['night']!=page.root.name:
        raise ValueError('invalid redshift pointer')
    if sha256(manifest_path)!=pointer['sha256']:raise ValueError('redshift manifest changed')
    manifest=page.read(manifest_path)
    expected={str(parent/'run.json'):sha256(parent/'run.json')}
    if rescue:expected[str(rescue/'run.json')]=sha256(rescue/'run.json')
    if manifest['night']!=page.root.name or manifest['parent_run_sha256']!=expected:
        return {}
    records={}
    for item in manifest['results']:
        path=Path(item['path']);path.resolve().relative_to(page.root/'QC')
        if sha256(path)!=item['sha256']:raise ValueError('redshift record changed')
        record=page.read(path)
        for key in ('raw','product','images','diagnostic_arrays'):
            if sha256(Path(record[key]))!=record[key+'_sha256']:raise ValueError('redshift input or evidence changed: '+key)
        for figure,digest in record['figures'].items():
            if sha256(Path(figure))!=digest:raise ValueError('redshift figure changed')
        if sha256(Path(record['ned']['query_file']))!=record['ned']['query_sha256']:raise ValueError('NED query record changed')
        record['record_path']=str(path)
        records[Path(record['raw']).name]=record
    return records


def redshift_cells(record, *, standard=False):
    if standard:return ['—','—']
    if not record:return ['Not queried','Not measured']
    ned=record['ned'];candidate=ned.get('candidate');spectral=record['spectral']
    if candidate:
        value=redshift_label(candidate).replace('(phot)','(photometric)').replace('(spec)','(spectroscopic)')
        ned_text=(value+'; '+candidate['name']+f"; {candidate['separation_arcsec']:.1f} arcsec; candidate host")
    else:ned_text='Query unavailable' if ned['status']=='unavailable' else 'No galaxy within 30 arcsec'
    z=spectral.get('z_heliocentric');z_error=spectral.get('z_heliocentric_error')
    if z is not None and math.isfinite(z):
        detail='provisional wavelength' if not spectral['wavelength_validated'] else 'line-system candidate'
        # A literal sign survives html.escape; an entity would be double-escaped.
        value=f'{z:.4f}'+(f' ± {z_error:.4f}' if z_error is not None and math.isfinite(z_error) else '')
        text=f'{value} ({detail})'
    else:
        text={'no_reliable_line_system':'Insufficient matching lines','insufficient_data':'Insufficient data',
              'spatially_inconsistent':'Spatial check failed','ambiguous':'Ambiguous line system'}.get(spectral['status'],'No estimate')
    anchor='redshift-'+Path(record['raw']).stem
    return [escape(ned_text),f'<a href="#{escape(anchor)}">{escape(text)} ↓</a>']


def redshift_section(page, records):
    if not records:return ''
    # The enclosing section already carries the heading.
    content='<p>NED and spectral estimates are independent. '
    content+='NED identifies the nearest catalogue galaxy within 30 arcsec of the telescope pointing; the host association is unconfirmed. '
    content+='The spectral search uses near-trace 2D emission, requires at least three matching line groups and checks spatial consistency. '
    content+='Both redshifts use the heliocentric frame. Provisional wavelengths have an unknown systematic error; no line system means no reliable estimate, not a redshift of zero.</p>'
    from .naming import source_order
    for record in sorted(records.values(),key=source_order):
        spectral=record['spectral'];cells=redshift_cells(record)
        title=record['object']+' / Redshift evidence';anchor='redshift-'+Path(record['raw']).stem
        figures=[Path(p) for p in record['figures'] if p.endswith('.jpg')]
        links=[page.download(Path(record['record_path']),'Measurements and provenance')]
        links.extend(page.download(Path(p),'Figure PDF') for p in record['figures'] if p.endswith('.pdf'))
        content+=f'<article class="exposure" id="{escape(anchor)}"><h3>{escape(title)}</h3>'
        content+='<p>NED: '+cells[0]+'. Spectral: '+cells[1]+'.</p>'
        candidate=record['ned'].get('candidate')
        if candidate and candidate['metadata'].get('z') is not None and spectral.get('z_heliocentric') is not None:
            difference=abs(float(candidate['metadata']['z'])-spectral['z_heliocentric'])
            if difference>.005:
                content+='<p class="qc-status-bad">The catalogue and spectral estimates differ. Check the catalogue measurement method and source association before assigning a host redshift.</p>'
        if spectral.get('z') is not None:
            sol=spectral['solutions'][0]
            content+='<p>Matched groups: '+escape(', '.join(sol['consistent_groups']))
            content+=f" ({sol['number_of_groups']} independent narrow groups)."
            content+=f" Uncertainty in z: {sol.get('z_error',sol['z_stat_error']):.2g}"
            content+=f" (inverse-variance fit error {sol['z_stat_error']:.2g} with blend floors"
            if sol.get('z_scatter_error') is not None:
                content+=f"; group-to-group standard error {sol['z_scatter_error']:.2g}"
            content+='); the larger of the two is quoted. Excludes wavelength, background and resampling systematics.</p>'
        content+='<p>'+ ' · '.join(links)+'</p>'
        content+=page.figure(figures[0] if figures else None,title,full_width=True)+'</article>'
    return content
