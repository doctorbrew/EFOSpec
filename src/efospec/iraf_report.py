"""Render saved, hash-bound IRAF overlays inside the existing nightly page."""
from pathlib import Path

from .inventory import sha256


def write_comparison_page(page, revision, content):
    """Publish a separate supplement using the same offline nightly renderer."""
    from .epoch_report import CSS, EPOCH_CSS, SCRIPT, _text
    from .report_assets import write_report_bundle
    night=page.root.name
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EFOSpec / {night} / IRAF comparison</title><style>{CSS}{EPOCH_CSS}</style></head>
<body><main><header class="masthead"><span class="brand">ePESSTO+ / EFOSpec</span></header>
<div class="intro"><div><span class="eyebrow">IRAF comparison</span><h1>{night}</h1></div></div>
<p><a href="index.html">Nightly log</a></p>
<section class="target" id="iraf-comparison"><h2>IRAF comparison</h2>{content}</section>
<footer>EFOSpec · {night} · Processing revision {_text(revision.name)}</footer></main>
<dialog aria-label="Enlarged figure"><button type="button">Close</button><img alt=""></dialog>
<script>{SCRIPT}</script></body></html>'''
    return write_report_bundle(page.root/'iraf-comparison.html',html)


def comparison_section(page, revision):
    from .epoch_report import _text, _table
    root=revision/'iraf-comparison'
    pointer_path=root/'current.json'
    if not pointer_path.exists():
        return ''
    pointer=page.read(pointer_path)
    output=(root/pointer['path']).resolve()
    if output.parent!=root.resolve():raise ValueError('invalid IRAF comparison pointer')
    manifest=output/'comparison.json'
    if sha256(manifest)!=pointer['sha256']:raise ValueError('IRAF comparison manifest changed')
    record=page.read(manifest)
    if record['parent_sha256']!=sha256(revision/'reduction/run.json'):
        return '<p class="qc-status-bad">IRAF comparison belongs to an earlier reduction; regenerate it.</p>'
    text='<p>Historical PESSTO / IRAF reductions, matched to the same raw exposures. '
    text+='Delivered wavelengths and absolute flux are overlaid without shifts or normalization. '
    text+='Agreement is not independent validation; IRAF wavelength medium/frame may be unspecified.</p>'
    text+='<p>Matching identifies the raw exposure, not necessarily the same source. '
    text+='Compare the saved aperture records and detector geometry before interpreting flux differences.</p>'
    text+='<p>'+page.download(manifest,'Comparison provenance (JSON)')+'</p>'
    for error in record['scan_errors']:
        text+='<p class="qc-status-bad">'+_text(error['path']+': '+error['error'])+'</p>'
    if not record['candidates']:
        return text+'<p>No supported IRAF flux products were found beside this night’s raw data.</p>'
    rows=[]
    for item in record['candidates']:
        rows.append([_text(item['object']),_text(Path(item['path']).name),
                     ('<span class="qc-status-bad">'+_text(item['status'])+'</span>'
                      if item['status']!='compared' else 'Compared'),
                     _text(item.get('reason',item.get('match_method','')))])
        if item['status']!='compared':continue
        for key, digest_key in [('path','sha256'),('native_product','native_sha256')]:
            if sha256(Path(item[key]))!=item[digest_key]:raise ValueError('IRAF comparison input changed')
        for key,digest in item['figure_sha256'].items():
            if sha256(Path(item[key]))!=digest:raise ValueError('IRAF comparison figure changed')
        text+='<article><h3>'+_text(item['object'])+'</h3>'
        text+='<p class="caption">'+_text(Path(item['path']).name)+'</p>'
        text+='<p class="caption">Saved APNUM1 (aperture, beam, lower/upper limits): IRAF '
        text+=_text(item['iraf'].get('aperture','unspecified'))+'; EFOSpec '+_text(item['native'].get('aperture','unspecified'))
        text+='. These are product coordinates; inspect trim/transform records before registering apertures.</p>'
        text+=page.figure(Path(item['jpg']),item['object']+' / IRAF comparison',full_width=True)
        text+='<p>'+page.download(Path(item['pdf']),'PDF')+' · '+page.download(Path(item['jpg']),'JPG')+'</p></article>'
    text+=_table(['Object','IRAF product','Comparison status','Association / limitation'],rows)
    if record['unmatched_native']:
        text+='<p>Native spectra without a comparison: '+_text(', '.join(r['object'] for r in record['unmatched_native']))+'.</p>'
    return text
