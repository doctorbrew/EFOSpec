"""Explicit presentation selection for checked native manual recovery trials."""
from .native_sky import wavelength_accepted
import json
from pathlib import Path
from .inventory import sha256


def selected_manual_recoveries(parent):
    parent=Path(parent).resolve();pointer=parent.parent/'QC/manual-recovery-selection.json'
    if not pointer.exists():return []
    selection=json.loads(pointer.read_text())
    if selection['parent_sha256']!=sha256(parent/'run.json'):raise ValueError('manual recovery parent changed')
    records=[]
    for item in selection['runs']:
        path=Path(item['path']).resolve()
        if not path.is_relative_to(parent.parent/'QC'):raise ValueError('manual recovery outside dated revision')
        for name,digest in item['sha256'].items():
            file=Path(name).resolve()
            if not file.is_relative_to(path) or sha256(file)!=digest:raise ValueError('manual recovery product changed')
        if str(path/'run.json') not in item['sha256']:raise ValueError('manual recovery manifest is not bound')
        run=json.loads((path/'run.json').read_text())
        if run.get('parent_sha256')!=selection['parent_sha256'] or run.get('execution_status')!='complete':raise ValueError('manual recovery is incomplete or stale')
        for result in run['results']:
            if not wavelength_accepted(result['sky_flexure']):raise ValueError('manual recovery wavelength check failed')
            if sha256(Path(result['raw']))!=result['raw_sha256']:raise ValueError('manual recovery raw changed')
            for key in ('product','native_spec1d'):
                if result[key] not in item['sha256']:raise ValueError('unbound manual recovery product')
        records.append((path,run))
    return records
