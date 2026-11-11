"""Offline catalogue evidence in the existing Source QC report section."""
from pathlib import Path

from .inventory import sha256
from .naming import source_order


def catalogue_qc(page, run):
    from .epoch_report import _text, _table
    from .field_catalogues import galaxy_labels, redshift_label
    from .typing_report import acquisition_metadata
    current = page.read(page.root/'QC/catalogue-current.json')
    if not current: return []
    if current.get('night') != page.root.name: raise ValueError('catalogue report night mismatch')
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
        content = '<h3>'+_text(field['object']+' / Potential host galaxies')+'</h3><p class="caption">'+_text(Path(field['raw']).name)+'</p>'
        if field['status'] == 'failed':
            log = page.root/current['fields'][field['raw']]['path']
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
            sections.append((source_order(field), '<article class="exposure">'+content+status+'<p>'+download+'</p>'+acquisition_metadata(page,field['object'])+'</article>'))
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
        status=[]
        for query in field['queries']:
            label=_text(query['status'].replace('_',' '))
            if query['status'] in ('unavailable','truncated'):label='<span class="qc-status-bad">'+label+'</span>'
            status.append([_text(query['catalogue']),label,'—' if query['status']=='unavailable' else len(query['rows'])])
        content += _table(['Catalogue','Query status','Sources in search cone'],status)
        if field.get('target_position', {}).get('status') == 'projected':
            content += '<p class="caption">The named open circle marks the observing-block target RA/Dec projected through the measured image astrometry. This position does not establish the slit centre or identify a spectral trace.</p>'
        content += '<p class="caption">Galaxy markers show catalogue-classified candidates. The detail view frames the galaxy candidates and registered target. The SN is blue and galaxy candidates are red, with translucent white label boxes; galaxy numbers match across both panels and this table. The shared legend below the images gives redshift z and its catalogue method (spec or phot); unavailable values or methods are stated explicitly. AllWISE counterparts remain in the table, without separate image markers. Positional neighbours use a 2-arcsec radius and are not confirmed cross-identifications.</p>'
        content += '<div class="qc-plots">'+page.figure(image,field['object']+' / Potential host galaxies',full_width=True)+'</div>'
        content += acquisition_metadata(page,field['object'])
        rows=[]
        labels=galaxy_labels(field['sources'])
        for source in field['sources']:
            if not source['galaxy_candidate']:continue
            neighbours='; '.join(n['catalogue']+' '+n['name']+f' ({n["separation_arcsec"]:.2f} arcsec)' for n in source['positional_neighbours']) or 'None within 2 arcsec'
            rows.append([labels[source['id']],_text(source['catalogue']),_text(source['name']),
                         f'{source["ra"]:.6f}, {source["dec"]:.6f}',
                         _text(redshift_label(source)),_text(neighbours)])
        content += _table(['Marker','Catalogue','Galaxy candidate','ICRS RA, Dec (deg)','Redshift / method','Positional neighbours'],rows) if rows else '<p>No catalogue-classified galaxies returned inside this image by the available queries.</p>'
        links=[page.download(Path(p),Path(p).suffix[1:].upper()+' overlay') for p in field['figures_sha256']]
        content += '<p>'+' · '.join(links)+'</p>'
        sections.append((source_order(field), '<article class="exposure">'+content+'</article>'))
    return sections
