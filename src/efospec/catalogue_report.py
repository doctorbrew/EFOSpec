"""Offline catalogue evidence in the existing Source QC report section."""
from pathlib import Path

from .inventory import sha256
from .naming import source_order


def nearest_catalogue_redshift(query, field):
    """Nearest catalogue galaxy within 30 arcsec; never borrow a farther z."""
    from astropy.coordinates import SkyCoord
    from astropy import units as u
    from .field_catalogues import redshift_label
    position=field.get('target_position',{}).get('icrs_deg')
    if not position or query['status']=='unavailable':return '—'
    target=SkyCoord(*position,unit='deg');matches=[]
    for row in query['rows']:
        if not row.get('galaxy_candidate'):continue
        distance=float(target.separation(SkyCoord(row['ra']*u.deg,row['dec']*u.deg)).arcsec)
        if distance<=30:matches.append((distance,row))
    if not matches:return 'No galaxy within 30 arcsec'
    distance,row=min(matches,key=lambda item:item[0])
    return f"{redshift_label(row)}; {row['name']} ({distance:.1f} arcsec)"


def field_redshifts(page, field):
    raws={Path(r['path']).name for r in field['science_raws']}
    return {k:v for k,v in getattr(page,'redshift_records',{}).items()
            if Path(v['raw']).name in raws and v['object']==field['object']}


def host_line_evidence(page, records):
    from .redshift_report import redshift_section
    used=getattr(page,'embedded_redshift_raws',set())
    selected={k:v for k,v in records.items() if k not in used}
    page.embedded_redshift_raws=used|set(selected)
    return redshift_section(page,selected,include_intro=False)


def catalogue_qc(page, run):
    from .epoch_report import _text, _table
    from .field_catalogues import galaxy_labels, redshift_label
    from .typing_report import acquisition_metadata, emission_cell
    current = page.read(page.root/'QC/catalogue-current.json')
    if not current: current = {'night':page.night,'fields':{}}
    if current.get('night') != page.night: raise ValueError('catalogue report night mismatch')
    science = {Path(r.get('raw',r.get('path',''))).name for key in ('results','errors','skipped') for r in run.get(key,[])}
    fields = []
    for item in current['fields'].values():
        path = page.root/item['path']; path.resolve().relative_to(page.root)
        if sha256(path) != item['sha256']: raise ValueError('catalogue QC record changed')
        field = page.read(path)
        if not any(Path(r['path']).name in science for r in field['science_raws']): continue
        if any(sha256(Path(r['path'])) != r['sha256'] for r in field['science_raws']):
            raise ValueError('catalogue-associated science raw changed')
        if sha256(Path(field['raw'])) != field['raw_sha256']: raise ValueError('catalogue acquisition changed')
        fields.append(field)
    sections = []
    for field in sorted(fields, key=lambda f:(source_order(f),f['raw'])):
        measurements=field_redshifts(page,field)
        content = '<h3>'+_text(field['object']+' / Potential host galaxies')+'</h3><p class="caption">'+_text(Path(field['raw']).name)+'</p>'
        status=[]
        for query in field.get('queries',[]):
            label=_text(query['status'].replace('_',' '))
            if query['status'] in ('unavailable','truncated'):label='<span class="qc-status-bad">'+label+'</span>'
            status.append([_text(query['catalogue']),label,'—' if query['status']=='unavailable' else len(query['rows']),_text(nearest_catalogue_redshift(query,field))])
        from .redshift_report import redshift_cells
        for record in measurements.values():
            spectral=record['spectral'];groups=spectral['solutions'][0]['number_of_groups'] if spectral.get('solutions') else 0
            status.append(['2D spectrum · Host lines',_text(spectral['status'].replace('_',' ')),
                           f'{groups} matching groups',redshift_cells(record)[1]])
        content += _table(['Source','Query status','Sources in search cone','Best-match redshift'],status)
        content += '<p class="caption">Catalogue match: nearest galaxy within 30 arcsec of the registered target. 2D emission is measured independently; host association is unconfirmed.</p>'
        if field['status'] == 'failed':
            log = Path(field.get('display_parent_record',{}).get('path',page.root/current['fields'][field['raw']]['path']))
            download = page.download(log.parent/'astrometry/solve.log', 'Astrometry log')
            from .acquisition_target import target_position
            target = target_position(field['raw'], field['object'])
            if target['status'] in ('projected', 'outside_image'):
                a = target['astrometry']
                status = ('<p>Newer target-position astrometry is available: '
                          +str(a['matched_stars'])+f' matched stars; RMS {target["astrometry_rms_pixel"]:.2f} pixels. '
                          'This retained catalogue attempt has no galaxy overlay.</p>')
            else:
                status = '<p class="qc-status-bad">'+_text(field['error'])+'</p>'
            sections.append((source_order(field), '<article class="exposure">'+content+status+'<p>'+download+'</p>'+acquisition_metadata(page,field['object'],show_candidates=True)+host_line_evidence(page,measurements)+'</article>'))
            continue
        for name, digest in field['figures_sha256'].items():
            p=Path(name);p.resolve().relative_to(page.root)
            if sha256(p)!=digest: raise ValueError('catalogue overlay changed')
        image=Path(field['preview']);image.resolve().relative_to(page.root)
        if sha256(image)!=field['preview_sha256']:raise ValueError('catalogue preview changed')
        a=field['astrometry']
        if sha256(Path(a['wcs']))!=a['wcs_sha256']:raise ValueError('catalogue WCS changed')
        content += '<p>Local astrometry: '+str(a['matched_stars'])+f' matched stars; RMS {a["rms_pixel"]:.2f} pixels. '
        content += 'Catalogue positions and nearby counterparts are provisional; no host or spectral-trace identity is assigned.</p>'
        content += '<div class="qc-plots">'+page.figure(image,field['object']+' / Potential host galaxies',full_width=True)+'</div>'
        content += acquisition_metadata(page,field['object'])
        rows=[]
        labels=galaxy_labels(field['sources'])
        for source in field['sources']:
            if not source['galaxy_candidate']:continue
            neighbours='; '.join(n['catalogue']+' '+n['name']+f' ({n["separation_arcsec"]:.2f} arcsec)' for n in source['positional_neighbours']) or 'None within 2 arcsec'
            rows.append([labels[source['id']],_text(source['catalogue']),_text(source['name']),
                         f'{source["ra"]:.6f}, {source["dec"]:.6f}',
                         _text(redshift_label(source)) if source['catalogue']=='NED' else '—',
                         next((emission_cell(page,r,source['name']) for r in getattr(page,'typing_annotations',{}).values()
                               if r['object_id']==field['object'] and r.get('host_name')==source['name']), 'Not associated'),
                         _text(neighbours)])
        content += _table(['Marker','Catalogue','Galaxy candidate','ICRS RA, Dec (deg)','z (NED)','z (Host Emission)','Positional neighbours'],rows) if rows else '<p>No catalogue-classified galaxies returned inside this image by the available queries.</p>'
        links=[page.download(Path(p),Path(p).suffix[1:].upper()+' overlay') for p in field['figures_sha256']]
        content += '<p>'+' · '.join(links)+'</p>'
        content += host_line_evidence(page,measurements)
        sections.append((source_order(field), '<article class="exposure">'+content+'</article>'))
    # Keep associations without a catalogue image in this same report section.
    for obj in dict.fromkeys(r['object_id'] for r in getattr(page,'typing_annotations',{}).values()):
        remaining=acquisition_metadata(page,obj,show_candidates=True)
        if remaining:
            sections.append((source_order({'object':obj}), '<article class="exposure"><h3>'+_text(obj+' / Potential host galaxies')
                +'</h3><p>No saved catalogue acquisition overlay for this target.</p>'+remaining+'</article>'))
    return sections
