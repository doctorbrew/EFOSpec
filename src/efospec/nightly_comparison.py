"""Optional hash-bound replay evidence within the main nightly archive."""
import json
from pathlib import Path
from .inventory import sha256


def comparison_section(page, revision):
    from .epoch_report import _text, _table
    path=revision/'QC/nightly-comparison/comparison.json'
    if not path.exists():return ''
    record=json.loads(path.read_text())
    if record['parent_sha256']!=sha256(revision/'reduction/run.json'):
        raise ValueError('nightly comparison belongs to another reduction')
    for name,digest in record['input_sha256'].items():
        if sha256(Path(name))!=digest:raise ValueError('nightly comparison input changed')
    content='<h3>Fresh reduction compared with retained products</h3>'
    content+=''.join('<p>'+_text(s)+'</p>' for s in record['summary'])
    rows=[]
    for item in record['science']:
        rows.append([_text(item['object']),f"{item['exposure_time']:.2f}",
            _text(item['baseline_status']),_text(item['previous_selected_status']),
            _text(item['current_status']),_text(item['comparison_note'])])
    content+=_table(['Source','Seconds','Previous full run','After previous manual review',
                     'Fresh run','Comparison on common valid samples'],rows)
    content+='<details><summary>Prior and fresh spectra on the same scale</summary>'
    for item in record['science']:
        figure=Path(item['figure'])
        figure.resolve().relative_to(path.parent.resolve())
        if sha256(figure)!=item['figure_sha256']:raise ValueError('comparison figure changed')
        content+=page.figure(figure,item['object']+' / Previous selected and fresh extraction',full_width=True)
    return content+'</details>'
