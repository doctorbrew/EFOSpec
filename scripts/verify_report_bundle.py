#!/usr/bin/env python3
"""Verify one dated report's compact/portable bytes and offline interactions."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from efospec.report_assets import DATA_URL,EXTENSIONS
from efospec.inventory import sha256


def verify(night,project_root='.'):
    from datetime import date
    from playwright.sync_api import sync_playwright
    if date.fromisoformat(night).isoformat()!=night:raise ValueError('invalid observing date')
    root=Path(project_root).resolve()/'runs'/night
    page_path=root/'index.html';portable=root/'index-portable.html'
    manifest=json.loads((root/'report-assets/index-manifest.json').read_text())
    assert sha256(portable)==manifest['portable_sha256']
    checked=0
    for match in DATA_URL.finditer(portable.read_text()):
        payload=base64.b64decode(match.group(2),validate=True)
        digest=hashlib.sha256(payload).hexdigest()
        path=root/'report-assets'/(digest+EXTENSIONS.get(match.group(1),'.bin'))
        assert path.read_bytes()==payload;checked+=1
    assert checked>=len(manifest['assets'])
    with sync_playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context(offline=True,accept_downloads=True,
            viewport=dict(width=1440,height=900))
        page=context.new_page();errors=[];external=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:external.append(request.url) if request.url.startswith(('http://','https://')) else None)
        start=time.monotonic();page.goto(page_path.as_uri(),wait_until='load')
        load_seconds=time.monotonic()-start
        assert page.locator('h1').inner_text()==night
        page.locator('img').evaluate_all('(images)=>images.forEach(i=>i.loading="eager")')
        page.wait_for_function('Array.from(document.images).every(i=>!i.getAttribute("src")||(i.complete&&i.naturalWidth>0))')
        page.locator('button.enlarge').first.click();assert page.locator('dialog').is_visible()
        page.keyboard.press('Escape');assert not page.locator('dialog').is_visible()
        ids=page.locator('[id]').evaluate_all('(els)=>els.map(e=>e.id)')
        assert len(ids)==len(set(ids))
        links=page.locator('a[href^="#"]').evaluate_all('(els)=>els.map(e=>e.getAttribute("href").slice(1))')
        assert set(links)<=set(ids)
        downloads=[];anchors=page.locator('a[download]')
        info=anchors.evaluate_all('(els)=>els.map(e=>({name:e.getAttribute("download"),href:e.getAttribute("href")}))')
        for extension in ('.fits','.asci','.pdf'):
            index=next(i for i,r in enumerate(info) if r['name'].endswith(extension))
            source=root/info[index]['href']
            with page.expect_download() as event:anchors.nth(index).click()
            assert Path(event.value.path()).read_bytes()==source.read_bytes()
            downloads.append(dict(name=info[index]['name'],sha256=sha256(source)))
        page.set_viewport_size(dict(width=390,height=844))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors and not external
        viewer=context.new_page();viewer_requests=[]
        viewer.on('request',lambda request:viewer_requests.append(request.url))
        viewer.set_content(page_path.read_text(),wait_until='load')
        viewer.locator('img').evaluate_all('(images)=>images.forEach(i=>i.loading="eager")')
        viewer.wait_for_function('Array.from(document.querySelectorAll(".enlarge img")).every(i=>i.complete&&i.naturalWidth>0)')
        viewer_figures=viewer.locator('.enlarge img').count()
        viewer.locator('button.enlarge').first.click()
        assert viewer.locator('dialog').is_visible()
        viewer.wait_for_function('document.querySelector("dialog img").naturalWidth>0')
        viewer.keyboard.press('Escape')
        assert not viewer_requests
        output=dict(status='passed',night=night,entry_bytes=page_path.stat().st_size,
            portable_bytes=portable.stat().st_size,unchanged_embedded_payloads=checked,
            displayed_images=page.locator('img[src]').count(),downloads=downloads,
            offline=True,load_seconds=round(load_seconds,3),viewports=[1440,390],
            originless_viewer_figures=viewer_figures,originless_viewer_requests=viewer_requests,
            javascript_errors=errors,external_requests=external,entry_sha256=sha256(page_path))
        context.close();browser.close()
    (root/'report-assets/opening-verification.json').write_text(json.dumps(output,indent=2)+'\n')
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('night');p.add_argument('--project-root',default='.')
    a=p.parse_args();print(json.dumps(verify(a.night,a.project_root)))
