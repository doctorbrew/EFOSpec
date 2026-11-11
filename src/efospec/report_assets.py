"""Viewer-safe illustrated reports plus complete, single-file portable exports.

Keep scientific downloads unchanged. Embed web figure previews so HTML viewers
need no filesystem base URL; load bulky downloads from siblings only on demand.
"""
import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path
import re

DATA_URL=re.compile(r'data:([a-zA-Z0-9.+/-]+);base64,([A-Za-z0-9+/]*={0,2})')
EXTENSIONS={'image/jpeg':'.jpg','image/png':'.png','application/pdf':'.pdf',
            'application/json':'.json','text/plain':'.txt','text/csv':'.csv'}
DOWNLOAD_LINK=re.compile(r'(<a\b[^>]*\bdownload="[^"]*"[^>]*\bhref=")(report-assets/[a-f0-9]+\.[a-z]+)("[^>]*>)')
DOWNLOAD_SCRIPT='''
window.efospecReportPayloads = Object.create(null);
document.addEventListener('click', function(event) {
  const link = event.target.closest('a[data-download-script]');
  if (!link || event.button !== 0 || event.ctrlKey || event.metaKey) return;
  event.preventDefault();
  if (link.getAttribute('aria-busy') === 'true') return;
  link.setAttribute('aria-busy', 'true');
  const script = document.createElement('script');
  const key = link.dataset.downloadKey;
  script.src = link.dataset.downloadScript;
  function done() { script.remove(); link.removeAttribute('aria-busy'); }
  script.onload = function() {
    const payload = window.efospecReportPayloads[key];
    try {
      if (!payload) throw new Error('Missing saved download payload');
      const raw = atob(payload.data), bytes = new Uint8Array(raw.length);
      for (let i=0; i<raw.length; i++) bytes[i] = raw.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([bytes], {type: payload.mime}));
      const download = document.createElement('a');
      download.href = url; download.download = link.download;
      document.body.appendChild(download); download.click(); download.remove();
      setTimeout(function() { URL.revokeObjectURL(url); }, 60000);
    } finally { delete window.efospecReportPayloads[key]; done(); }
  };
  script.onerror = function() {
    done(); link.title = 'Download unavailable: keep report-assets beside index.html';
  };
  document.body.appendChild(script);
});
'''


def write_report_bundle(destination, html):
    """Publish local HTML last; retain a self-contained export alongside it."""
    destination=Path(destination).resolve();root=destination.parent
    if 'data-report-assets="local"' in html:
        raise ValueError('use the embedded portable source, not an already compact report')
    assets=root/'report-assets';assets.mkdir(exist_ok=True)
    assets.resolve().relative_to(root)
    records={}

    def relocate(match):
        mime=match.group(1);payload=base64.b64decode(match.group(2),validate=True)
        digest=hashlib.sha256(payload).hexdigest()
        name=digest+EXTENSIONS.get(mime,'.bin');path=assets/name
        path.resolve().relative_to(assets.resolve())
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError('saved report asset changed: '+name)
        else:
            temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_bytes(payload);temporary.replace(path)
        records[name]=dict(sha256=digest,bytes=len(payload),mime=mime)
        if mime.startswith('image/'):
            if mime not in ('image/jpeg','image/png','image/webp'):
                return match.group(0)
            from PIL import Image
            with Image.open(BytesIO(payload)) as source:
                preview=source.convert('RGB')
                preview.thumbnail((1200,1200),Image.Resampling.LANCZOS)
                buffer=BytesIO();preview.save(buffer,format='WEBP',quality=85,method=4)
                encoded=buffer.getvalue()
            records[name]['inline_preview']=dict(mime='image/webp',maximum_dimension=1200,quality=85,
                sha256=hashlib.sha256(encoded).hexdigest(),bytes=len(encoded))
            return 'data:image/webp;base64,'+base64.b64encode(encoded).decode()
        return 'report-assets/'+name

    compact=DATA_URL.sub(relocate,html)
    def download_payload(match):
        relative=match.group(2);name=Path(relative).name;record=records[name]
        key=record['sha256'];script_path=assets/(key+'.js')
        payload=dict(mime=record['mime'],data=base64.b64encode((root/relative).read_bytes()).decode())
        # Classic sibling scripts work from file:// without a server or fetch
        # permissions. The bytes are loaded only after a download is clicked.
        script='window.efospecReportPayloads['+json.dumps(key)+']='+json.dumps(payload)+';\n'
        script_path.write_text(script)
        record['download_script']=script_path.name
        record['download_script_sha256']=hashlib.sha256(script.encode()).hexdigest()
        return match.group(1)+relative+'" data-download-script="report-assets/'+script_path.name+'" data-download-key="'+key+match.group(3)
    compact=DOWNLOAD_LINK.sub(download_payload,compact)
    compact=compact.replace('</body>','<script>'+DOWNLOAD_SCRIPT+'</script></body>',1)
    portable=destination.with_name(destination.stem+'-portable.html')
    note=(f'<p class="caption" data-report-assets="local">'
          f'<a href="{portable.name}">'
          'Self-contained report</a>. '
          'Figures are included in this page. For file downloads, open the report '
          'in Chrome or Safari with its report-assets folder alongside.</p>')
    compact=compact.replace('</footer>',note+'</footer>',1) if '</footer>' in compact else compact.replace('</body>',note+'</body>',1)
    # T3 binds out-of-workspace previews to a file's device/inode. Replacing
    # index.html invalidates cached URLs, even when the HTML itself is valid.
    # Keep a content-named copy beside the assets for stable viewer links.
    viewer_bytes=compact.encode()
    viewer_digest=hashlib.sha256(viewer_bytes).hexdigest()
    viewer=destination.with_name(destination.stem+'-view-'+viewer_digest[:12]+'.html')
    if viewer.exists():
        if viewer.read_bytes()!=viewer_bytes:
            raise ValueError('saved report viewer copy changed: '+viewer.name)
    else:
        with viewer.open('xb') as stream:
            stream.write(viewer_bytes)
    # Portable and manifest writes complete before replacing the entry point.
    temp=portable.with_suffix('.html.tmp');temp.write_text(html);temp.replace(portable)
    manifest=assets/(destination.stem+'-manifest.json')
    manifest.write_text(json.dumps(dict(portable_html=portable.name,
        portable_sha256=hashlib.sha256(html.encode()).hexdigest(),
        viewer_html=viewer.name,viewer_sha256=viewer_digest,assets=records),indent=2)+'\n')
    temp=destination.with_suffix('.html.tmp');temp.write_text(compact);temp.replace(destination)
    return dict(path=str(destination),bytes=destination.stat().st_size,portable_path=str(portable),
                portable_bytes=portable.stat().st_size,viewer_path=str(viewer),assets=len(records))


def compact_existing_report(night, *, project_root='.'):
    """Repair one existing dated report without re-reading reduction state."""
    from datetime import date,datetime,timezone
    from shutil import copy2
    if date.fromisoformat(night).isoformat()!=night:raise ValueError('invalid observing night')
    root=Path(project_root).resolve()/'runs'/night;path=root/'index.html'
    html=path.read_text()
    if 'data-report-assets="local"' in html:raise ValueError('report is already compact')
    archive=root/'archive/reports';archive.mkdir(parents=True,exist_ok=True)
    backup=archive/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%f')+'-before-compact.html')
    copy2(path,backup)
    return dict(write_report_bundle(path,html),archive=str(backup))
