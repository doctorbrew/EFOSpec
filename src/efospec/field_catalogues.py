"""Recorded NED, SDSS DR17 and AllWISE cone searches for acquisition QC."""
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import requests
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy import units as u

from .inventory import sha256

CATALOGUES = ('NED', 'SDSS', 'AllWISE')
MAX_ROWS = 2000


def galaxy_labels(sources):
    """Number galaxy candidates consistently across both panels and the table."""
    galaxies = [s for s in sources if s['galaxy_candidate']]
    return {s['id']: f'Galaxy {i}' for i, s in enumerate(galaxies, 1)}


def redshift_label(source):
    """Use the catalogue's measurement flag, never infer a method from z."""
    metadata = source['metadata']
    z = metadata.get('z')
    if z is None or not math.isfinite(float(z)):
        return 'z unavailable'
    flag = str(metadata.get('zflag') or '').strip().upper()
    method = {'S': 'spec', 'P': 'phot'}.get(flag[:1], 'method unknown')
    if '?' in flag:
        method += '; uncertain'
    return f'z={float(z):.6g} ({method})'


def query_spec(catalogue, ra, dec, radius):
    if not np.isfinite([ra, dec, radius]).all() or not 0 <= ra < 360 or not -90 <= dec <= 90 or not 0 < radius <= 10:
        raise ValueError('invalid catalogue cone (maximum radius 10 arcmin)')
    if catalogue == 'NED':
        # NED interprets bare equatorial longitude as hours: explicitly use d.
        return 'https://ned.ipac.caltech.edu/NED::API/ConeSearchByPosition', {
            'LON': f'{ra:.10f}d', 'LAT': f'{dec:.10f}d', 'RADIUS': radius,
            'CSYS': 'Equatorial', 'EQUINOX': 'J2000.0', 'MAXREC': MAX_ROWS}, 'votable'
    if catalogue == 'AllWISE':
        return 'https://irsa.ipac.caltech.edu/TAP/sync', {
            'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'votable',
            'QUERY': f"SELECT TOP {MAX_ROWS} designation,ra,dec,w1mpro,w2mpro,ext_flg,cc_flags FROM allwise_p3as_psd "
                     f"WHERE CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra},{dec},{radius/60.}))=1"}, 'votable'
    if catalogue == 'SDSS':
        return 'https://skyserver.sdss.org/dr17/SkyServerWS/SearchTools/SqlSearch', {
            'cmd': f'SELECT TOP {MAX_ROWS} p.objid,p.ra,p.dec,p.type,p.modelMag_r FROM PhotoObj AS p '
                   f'JOIN dbo.fGetNearbyObjEq({ra},{dec},{radius}) AS n ON p.objid=n.objid WHERE p.mode=1',
            'format': 'csv'}, 'ascii.csv'
    raise ValueError('unknown catalogue: '+catalogue)


def value(row, name):
    v = row[name]
    if np.ma.is_masked(v): return None
    if isinstance(v, bytes): return v.decode().strip()
    if isinstance(v, (float, np.floating)):
        return float(v) if np.isfinite(v) else None
    if isinstance(v, (int, np.integer)): return int(v)
    return str(v).strip()


def parse_catalogue(content, catalogue):
    if catalogue in ('NED', 'AllWISE'):
        for info in ET.fromstring(content).iter():
            if info.tag.rsplit('}', 1)[-1] == 'INFO' and info.get('value', '').upper() in ('ERROR', 'OVERFLOW'):
                raise ValueError('catalogue service '+str(info.get('value'))+': '+(info.text or ''))
        table = Table.read(BytesIO(content), format='votable', use_names_over_ids=catalogue == 'AllWISE')
    else:
        table = Table.read(BytesIO(content), format='ascii.csv', comment=r'\s*#')
    required = {'NED': ['prefname','ra','dec','ptype','z','zflag'],
                'SDSS': ['objid','ra','dec','type','modelMag_r'],
                'AllWISE': ['designation','ra','dec','w1mpro','w2mpro','ext_flg','cc_flags']}[catalogue]
    if not set(required) <= set(table.colnames):
        raise ValueError('unexpected '+catalogue+' response columns')
    result = []
    for row in table:
        r = {key: value(row, key) for key in required}
        if r['ra'] is None or r['dec'] is None or not 0 <= float(r['ra']) < 360 or not -90 <= float(r['dec']) <= 90:
            raise ValueError('catalogue contains invalid coordinates')
        sky = SkyCoord(float(r['ra'])*u.deg, float(r['dec'])*u.deg,
                       frame='fk5' if catalogue == 'NED' else 'icrs').icrs
        name = r[{'NED':'prefname','SDSS':'objid','AllWISE':'designation'}[catalogue]]
        galaxy = (r['ptype'] == 'G') if catalogue == 'NED' else (r['type'] is not None and int(r['type']) == 3 if catalogue == 'SDSS' else False)
        result.append({'catalogue':catalogue, 'name':str(name), 'ra':float(sky.ra.deg),
            'dec':float(sky.dec.deg), 'galaxy_candidate':galaxy, 'host_confirmed':False, 'metadata':r})
    return result


def fetch_catalogue(catalogue, centre, radius, directory, *, timeout=20):
    """Replay an exact recorded query from disk, including explicit failures."""
    url, params, form = query_spec(catalogue, *centre, radius)
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    path = directory/(catalogue+'.json')
    request = {'url':url, 'parameters':params}
    if path.exists():
        saved = json.loads(path.read_text())
        if saved['request'] != request: raise ValueError('cached catalogue query differs')
        if saved.get('response') and sha256(directory/saved['response']) != saved['response_sha256']:
            raise ValueError('cached catalogue response changed')
        return saved
    record = {'catalogue':catalogue, 'request':request, 'retrieved_utc':datetime.now(timezone.utc).isoformat()}
    try:
        response = requests.get(url, params=params, timeout=(min(timeout, 10), timeout))
        raw = directory/(catalogue+('.xml' if form == 'votable' else '.csv'))
        raw.write_bytes(response.content)
        record.update(response=raw.name, response_sha256=sha256(raw), http_status=response.status_code)
        response.raise_for_status()
        rows = parse_catalogue(response.content, catalogue)
        record.update(status='truncated' if len(rows) >= MAX_ROWS else ('ok' if rows else 'no_matches'), rows=rows)
    except Exception as exc:
        record.update(status='unavailable', error=str(exc), rows=[])
    path.write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    return record


def project_sources(queries, wcs, shape, *, match_arcsec=2.):
    """Project into acquisition pixels; retain all ambiguous positional neighbours."""
    if not np.isfinite(match_arcsec) or match_arcsec <= 0: raise ValueError('invalid cross-match radius')
    ny, nx = shape; sources = []
    for query in queries:
        for row in query['rows']:
            sky = SkyCoord(row['ra']*u.deg, row['dec']*u.deg, frame='icrs')
            x, y = (float(v) for v in wcs.world_to_pixel(sky))
            if np.isfinite([x, y]).all() and -.5 <= x < nx-.5 and -.5 <= y < ny-.5:
                sources.append(dict(row, x=x, y=y))
    sources.sort(key=lambda row:(CATALOGUES.index(row['catalogue']), row['name']))
    for i, row in enumerate(sources): row['id'] = f'{row["catalogue"][0]}{i+1}'
    if sources:
        sky = SkyCoord([s['ra'] for s in sources]*u.deg, [s['dec'] for s in sources]*u.deg)
        for i, row in enumerate(sources):
            separations = sky[i].separation(sky).arcsec
            row['positional_neighbours'] = [{'id':s['id'], 'catalogue':s['catalogue'], 'name':s['name'],
                'separation_arcsec':float(separations[j])} for j,s in enumerate(sources)
                if s['catalogue'] != row['catalogue'] and separations[j] <= match_arcsec]
    return sources
