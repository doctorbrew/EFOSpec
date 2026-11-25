"""Reviewed delivery identity and filenames; never infer a classification."""
import re
from .naming import science_stem


def reviewed_name(row, header):
    name = row.get('delivery_object') or row['object']
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ValueError('Invalid delivery_object')
    if any(ord(c) < 32 or ord(c) > 126 for c in name):
        raise ValueError('Delivery identity must be printable ASCII')
    if name != header['OBJECT']:
        evidence = row.get('identity_evidence')
        if not isinstance(evidence, str) or not evidence.strip() or evidence.upper() in {'TODO', 'UNKNOWN', 'NULL'}:
            raise ValueError('Identity correction requires identity_evidence')
        if row.get('identity_reviewed') is not True:
            raise ValueError('Identity correction requires identity_reviewed')
    if row.get('iau_name') and row['iau_name'] != name:
        raise ValueError('iau_name must agree with the delivery object')
    return name


def delivery_filename(source, header, name):
    """Preserve an existing exposure counter/full-run MJD; canonicalize the stem."""
    if source.name.startswith('EFOSC.') or not source.name.endswith('_f.fits'):
        raise ValueError('Select reduced _f.fits, never raw EFOSC or count extraction files')
    token = re.sub(r'[^A-Za-z0-9_.+-]', '_', name.replace(' ', ''))
    stem = science_stem(token, header['DATE-OBS'], header['GRISM'], header['FILTER'], header['SLIT'])
    suffix = re.search(r'(_(?:\d+_)?[1-9]\d*)_f\.fits$', source.name)
    return stem + (suffix.group(1) if suffix else '_1') + '_f.fits'


def apply_identity(header, name, row):
    old = header['OBJECT']
    if old != name:
        if 'ORIGOBJ' not in header:
            header['ORIGOBJ'] = old
        header['HIERARCH EFOSPEC PREVIOUS OBJECT'] = old
        header['HIERARCH EFOSPEC IDENTITY EVIDENCE'] = row['identity_evidence']
        header['HIERARCH EFOSPEC IDENTITY REVIEWER'] = row['reviewer']
        header['HISTORY'] = 'Reviewed delivery identity revision; scientific arrays unchanged.'
    header['OBJECT'] = name
    for key in ('TARGET', 'ESO OBS TARG NAME'):
        if key in header:
            header[key] = name
