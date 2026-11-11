"""Large download payloads must not be parsed to open the normal report."""
import base64
import hashlib
import json
from pathlib import Path
import re
from io import BytesIO
import pytest
from PIL import Image
from efospec.report_assets import write_report_bundle,compact_existing_report


def sample_image():
    buffer=BytesIO();Image.new('RGB',(80,60),'#244d3d').save(buffer,format='JPEG')
    return buffer.getvalue()


def test_compact_entry_retains_exact_images_downloads_and_portable_copy(tmp_path):
    payload=b'fits bytes\x00\x01'*200000;encoded=base64.b64encode(payload).decode()
    image=base64.b64encode(sample_image()).decode()
    html=('<html><body><h1>2026-10-28</h1><a download="science.fits" href="data:application/octet-stream;base64,'+encoded+'">FITS</a>'
          '<img src="data:image/jpeg;base64,'+image+'"><img src="data:image/jpeg;base64,'+image+'">'
          '<footer>EFOSpec</footer></body></html>')
    r=write_report_bundle(tmp_path/'index.html',html);compact=(tmp_path/'index.html').read_text()
    assert r['bytes']<5000 and r['assets']==2
    assert (tmp_path/'index-portable.html').read_text()==html
    urls=re.findall(r'(?:href|src)="(report-assets/[^"]+)"',compact)
    assert len(urls)==1
    assert (tmp_path/urls[0]).read_bytes()==payload
    images=re.findall(r'<img src="(data:image/webp;base64,[^"]+)"',compact)
    assert len(images)==2 and images[0]==images[1]
    assert Image.open(BytesIO(base64.b64decode(images[0].split(',',1)[1]))).size==(80,60)
    assert 'download="science.fits"' in compact
    assert 'data-download-script="report-assets/' in compact
    manifest=json.loads((tmp_path/'report-assets/index-manifest.json').read_text())
    assert all(hashlib.sha256((tmp_path/'report-assets'/p).read_bytes()).hexdigest()==v['sha256'] for p,v in manifest['assets'].items())
    with pytest.raises(ValueError,match='already compact'):write_report_bundle(tmp_path/'index.html',compact)


def test_repair_archives_original_and_does_not_touch_scientific_files(tmp_path):
    root=tmp_path/'runs/2026-10-29';root.mkdir(parents=True)
    html='<html><body>saved report<footer>EFOSpec</footer></body></html>'
    (root/'index.html').write_text(html);(root/'product.fits').write_bytes(b'unchanged')
    r=compact_existing_report('2026-10-29',project_root=tmp_path)
    assert Path(r['archive']).read_text()==html
    assert (root/'product.fits').read_bytes()==b'unchanged'
    with pytest.raises(ValueError,match='already compact'):
        compact_existing_report('2026-10-29',project_root=tmp_path)


def test_viewer_link_survives_rebuilding_the_canonical_report(tmp_path):
    """T3's exact-file preview link must keep its original file identity."""
    first=write_report_bundle(tmp_path/'index.html','<html><body>First revision</body></html>')
    viewer=Path(first['viewer_path'])
    original=viewer.read_bytes();identity=viewer.stat().st_ino
    second=write_report_bundle(tmp_path/'index.html','<html><body>Second revision</body></html>')
    assert Path(second['viewer_path'])!=viewer
    assert viewer.parent==tmp_path
    assert viewer.read_bytes()==original and viewer.stat().st_ino==identity
    current=Path(second['viewer_path'])
    assert current.read_bytes()==(tmp_path/'index.html').read_bytes()
    current_identity=current.stat().st_ino
    repeated=write_report_bundle(tmp_path/'index.html','<html><body>Second revision</body></html>')
    assert repeated['viewer_path']==second['viewer_path']
    assert current.stat().st_ino==current_identity


def test_tampered_content_addressed_asset_stops_publication(tmp_path):
    html='<html><body><img src="data:image/jpeg;base64,'+base64.b64encode(sample_image()).decode()+'"></body></html>'
    write_report_bundle(tmp_path/'index.html',html)
    previous=(tmp_path/'index.html').read_bytes()
    next((tmp_path/'report-assets').glob('*.jpg')).write_bytes(b'changed')
    with pytest.raises(ValueError,match='asset changed'):write_report_bundle(tmp_path/'index.html',html)
    assert (tmp_path/'index.html').read_bytes()==previous


def test_compact_download_works_offline_from_file_url(tmp_path):
    from playwright.sync_api import sync_playwright
    payload=b'FITS bytes\x00\xff'*1000
    html='<html><body><a download="science.fits" href="data:application/octet-stream;base64,'+base64.b64encode(payload).decode()+'">FITS</a></body></html>'
    write_report_bundle(tmp_path/'index.html',html)
    with sync_playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context(offline=True,accept_downloads=True)
        page=context.new_page();page.goto((tmp_path/'index.html').as_uri())
        with page.expect_download() as event:page.get_by_role('link',name='FITS',exact=True).click()
        assert event.value.suggested_filename=='science.fits'
        assert Path(event.value.path()).read_bytes()==payload
        context.close();browser.close()


def test_figures_load_in_an_html_viewer_without_a_filesystem_base(tmp_path):
    from playwright.sync_api import sync_playwright
    html='<html><body><img src="data:image/jpeg;base64,'+base64.b64encode(sample_image()).decode()+'"></body></html>'
    write_report_bundle(tmp_path/'index.html',html)
    # Reproduce the right-pane viewer: it receives HTML, not a file:// page.
    with sync_playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context(offline=True)
        page=context.new_page();requests=[];page.on('request',lambda r:requests.append(r.url))
        page.set_content((tmp_path/'index.html').read_text(),wait_until='load')
        assert page.locator('img').evaluate('(img)=>img.complete&&img.naturalWidth===80')
        assert not requests
        context.close();browser.close()
