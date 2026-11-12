"""Display-only framing and styling for acquisition annotations."""
import numpy as np

ANNOTATION_COLORS = {'target': 'xkcd:dodger blue', 'galaxy': 'xkcd:red'}
TEXT_COLORS = {'target': 'xkcd:red', 'galaxy': 'black'}
LABEL_BOX = {'boxstyle': 'round,pad=0.15', 'facecolor': 'white',
             'edgecolor': 'none', 'alpha': 0.8}


def saved_candidates(raw):
    """Read existing hash-verified catalogue evidence; never query while plotting."""
    import json
    from pathlib import Path
    from .inventory import sha256
    raw=Path(raw).resolve()
    if raw.parent.parent.name!='data':return []
    root=raw.parent.parent.parent/'runs'/raw.parent.name
    pointer=root/'QC/catalogue-current.json'
    if not pointer.exists():return []
    current=json.loads(pointer.read_text())
    if current['night']!=root.name:raise ValueError('catalogue night mismatch')
    item=current['fields'].get(str(raw))
    if not item:return []
    path=(root/item['path']).resolve();path.relative_to(root)
    if sha256(path)!=item['sha256']:raise ValueError('saved catalogue changed')
    field=json.loads(path.read_text())
    if sha256(raw)!=field['raw_sha256']:raise ValueError('acquisition changed')
    return [s for s in field.get('sources',[]) if s['galaxy_candidate']]


def candidate_bounds(shape, galaxies, target=None):
    """Enclose every in-frame galaxy candidate and the registered target."""
    ny,nx=shape
    points=[(s['x'],s['y']) for s in galaxies
            if np.isfinite([s['x'],s['y']]).all() and -.5<=s['x']<nx-.5 and -.5<=s['y']<ny-.5]
    count=len(points)
    if target and target.get('status')=='projected':points.append(target['pixel_xy'])
    if not points:return (-.5,nx-.5,-.5,ny-.5),'No registered candidates'
    points=np.asarray(points);cx,cy=(points.min(axis=0)+points.max(axis=0))/2
    width=max(360.,float(np.ptp(points[:,0]))+160.)
    height=max(360.,float(np.ptp(points[:,1]))+160.)
    def interval(center,span,size):
        span=min(span,size);lo=np.clip(center-span/2,-.5,size-.5-span)
        return float(lo),float(lo+span)
    return (*interval(cx,width,nx),*interval(cy,height,ny)),('Galaxy candidates' if count else 'Target vicinity / no galaxy candidates')
