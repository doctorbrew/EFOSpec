"""Observing-block target coordinates on independently solved acquisition pixels."""
import json
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time

from .acquisition_astrometry import check_solution
from .inventory import sha256


def _packed_degrees(value, *, hours=False):
    """ESO numeric HHMMSS.s / signed DDMMSS.s, retaining a negative zero degree."""
    value = float(value)
    if not np.isfinite(value):
        raise ValueError('non-finite target coordinate')
    packed = abs(value)
    major = int(packed // 10000)
    minute = int((packed - major*10000) // 100)
    second = packed - major*10000 - minute*100
    limit = 24 if hours else 90
    if minute >= 60 or second >= 60 or major > limit or (major == limit and
            (hours or minute or second)) or (hours and value < 0):
        raise ValueError('invalid packed target coordinate')
    return float(np.copysign((major + minute/60 + second/3600)*(15 if hours else 1), value))


def target_coordinates(header, object_name):
    """Use the named OB target, never the offset telescope-pointing RA/DEC."""
    record = {'object':object_name, 'status':'coordinates_unavailable',
              'coordinate_source':'ESO TEL TARG ALPHA / DELTA (observing block)',
              'independent_catalogue_verification':False}
    keys = ('ESO TEL TARG ALPHA', 'ESO TEL TARG DELTA', 'ESO TEL TARG EQUINOX')
    if any(key not in header for key in keys):
        return dict(record, reason='Observing-block target coordinates unavailable')
    if str(header.get('ESO OBS TARG NAME', '')).strip().casefold() != object_name.strip().casefold():
        return dict(record, reason='Observing-block target name does not match the source')
    if header.get('ESO TEL TARG COORDTYPE') != 'M':
        return dict(record, reason='Target coordinates are not specified as mean coordinates')
    frame = str(header.get('RADESYS', header.get('RADECSYS', ''))).strip().lower()
    if frame not in ('fk5', 'icrs'):
        return dict(record, reason='Target coordinate reference frame unavailable or unsupported')
    try:
        ra = _packed_degrees(header[keys[0]], hours=True)
        dec = _packed_degrees(header[keys[1]])
        equinox = float(header[keys[2]])
        if not np.isfinite(equinox):
            raise ValueError('invalid target equinox')
        kwargs = {'equinox':Time(equinox, format='jyear')} if frame == 'fk5' else {}
        sky = SkyCoord(ra*u.deg, dec*u.deg, frame=frame, **kwargs)
    except (TypeError, ValueError) as exc:
        return dict(record, reason=str(exc))
    return dict(record, status='coordinates_available', frame=frame, equinox=equinox,
                ra_deg=ra, dec_deg=dec, icrs_deg=[float(sky.icrs.ra.deg), float(sky.icrs.dec.deg)],
                ra_hms=sky.ra.to_string(unit=u.hourangle, sep=':', precision=2, pad=True),
                dec_dms=sky.dec.to_string(unit=u.deg, sep=':', precision=2, pad=True, alwayssign=True))


def saved_astrometry(raw):
    """Find hash-bound local solutions without rerunning a solver while plotting."""
    raw = Path(raw).resolve()
    if raw.parent.parent.name != 'data':
        return None
    root = raw.parent.parent.parent/'runs'/raw.parent.name
    pointer = root/'QC/target-astrometry-current.json'
    if pointer.is_file():
        current = json.loads(pointer.read_text())
        if current['night'] != root.name:
            raise ValueError('target astrometry night mismatch')
        if str(raw) in current['solutions']:
            return current['solutions'][str(raw)]
    pointer = root/'QC/catalogue-current.json'
    if not pointer.is_file():
        return None
    current = json.loads(pointer.read_text())
    if current['night'] != root.name:
        raise ValueError('catalogue astrometry night mismatch')
    item = current['fields'].get(str(raw))
    if not item:
        return None
    path = root/item['path']
    path.resolve().relative_to(root)
    if sha256(path) != item['sha256']:
        raise ValueError('saved acquisition record changed')
    field = json.loads(path.read_text())
    return field.get('astrometry') if field['status'] != 'failed' else None


def target_position(raw, object_name, astrometry=None):
    raw = Path(raw).resolve()
    header = fits.getheader(raw)
    record = dict(target_coordinates(header, object_name), raw=str(raw), raw_sha256=sha256(raw))
    if record['status'] != 'coordinates_available':
        return record
    astrometry = astrometry if astrometry is not None else saved_astrometry(raw)
    if not astrometry or astrometry.get('status') != 'solved':
        return dict(record, status='unregistered', reason='No accepted image astrometry; position not marked')
    if Path(astrometry['raw']).resolve() != raw or astrometry['raw_sha256'] != record['raw_sha256']:
        raise ValueError('target astrometry belongs to a different acquisition')
    for key in ('wcs', 'correspondences'):
        if sha256(Path(astrometry[key])) != astrometry[key+'_sha256']:
            raise ValueError('target astrometry '+key+' changed')
    shape = (header['NAXIS2'], header['NAXIS1'])
    wcs, quality = check_solution(astrometry['wcs'], astrometry['correspondences'], shape)
    sky = SkyCoord(*record['icrs_deg'], unit=u.deg, frame='icrs')
    x, y = map(float, wcs.world_to_pixel(sky))
    if not np.isfinite([x,y]).all():
        raise ValueError('target projection is non-finite')
    inside = -.5 <= x < shape[1]-.5 and -.5 <= y < shape[0]-.5
    return dict(record, status='projected' if inside else 'outside_image',
                pixel_xy=[x,y], pixel_origin=0, astrometry=astrometry,
                astrometry_rms_pixel=quality['rms_pixel'])


def draw_target_position(axes, record):
    """Open markers preserve the central source pixels; text identifies provenance."""
    from matplotlib.offsetbox import AnchoredText
    from .acquisition_display import ANNOTATION_COLORS, LABEL_BOX
    if 'ra_hms' not in record:
        return
    frame = f"FK5 J{record['equinox']:g}" if record['frame'] == 'fk5' else 'ICRS'
    label = (f"OB target / {frame}\n"
             f"RA {record['ra_hms']}\nDec {record['dec_dms']}")
    if record['status'] == 'unregistered':
        label += '\nPosition not registered'
    elif record['status'] == 'outside_image':
        label += '\nTarget outside image'
    key = AnchoredText(label, loc='upper left', prop={'size':18},
                       frameon=True, borderpad=.6, pad=.4)
    key.patch.set(facecolor='white', edgecolor='none', alpha=.9)
    key.set_gid('acquisition-target-coordinates'); key.set_zorder(10)
    axes[0].add_artist(key)
    if record['status'] != 'projected':
        return
    x, y = record['pixel_xy']
    for ax in axes:
        xlim, ylim = sorted(ax.get_xlim()), sorted(ax.get_ylim())
        if not (xlim[0] <= x <= xlim[1] and ylim[0] <= y <= ylim[1]):
            continue
        color=ANNOTATION_COLORS['target']
        marker = ax.scatter([x], [y], s=360, marker='o', facecolors='none',
                   edgecolors=[color], linewidths=2.8, zorder=8,
                   gid='acquisition-target-marker')
        ax.annotate(record['object'], (x,y), xytext=(16,0), textcoords='offset points',
                    va='center', fontsize=20, color=color, clip_on=True,
                    gid='acquisition-target-label', zorder=9, bbox=LABEL_BOX)
