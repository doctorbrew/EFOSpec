"""Exercise the actual browser editor and Python extraction worker together."""
import json
import os
import re
from pathlib import Path
import threading

import numpy as np
import pytest
from astropy.io import fits

from test_revisions import saved_exposure


def test_browser_recipe_roundtrip_two_source_extraction_and_result_download(saved_exposure, tmp_path):
    playwright = pytest.importorskip('playwright.sync_api')
    from efospec.workbench import Workbench, create_server
    from efospec.revisions import reextract
    run, reference, _ = saved_exposure
    app = Workbench(run,reference)
    # Browser test focuses on extraction; production workers also generate the existing report.
    command = app.worker_command
    app.worker_command = lambda *args: command(*args)+['--skip-report']
    server = create_server(app)
    thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[]
    try:
        with playwright.sync_playwright() as engine:
            kwargs = {'headless':True}
            if os.environ.get('EFOSPEC_TEST_CHROME'):
                kwargs['executable_path']=os.environ['EFOSPEC_TEST_CHROME']
            browser = engine.chromium.launch(**kwargs)
            page = browser.new_page(viewport={'width':1440,'height':1200})
            page.on('pageerror',lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/#{app.token}')
            page.get_by_role('status').filter(has_text='Original reduction loaded').wait_for()
            page.get_by_label('Source selection',exact=True).select_option('manual')
            page.get_by_label('primary FWHM (px)',exact=True).fill('4')
            page.get_by_label('primary FWHM (px)',exact=True).press('Tab')
            page.get_by_label('primary Half-width (px)',exact=True).fill('7')
            page.get_by_label('primary Half-width (px)',exact=True).press('Tab')
            page.get_by_role('button',name='+ Add second source').click()
            page.get_by_label('host Spatial pixel',exact=True).fill('397')
            page.get_by_label('host Spatial pixel',exact=True).press('Tab')
            page.get_by_label('Background',exact=True).select_option('regions')
            page.get_by_role('button',name='+ Add background band').click()
            page.get_by_label('include upper',exact=True).fill('329')
            page.get_by_label('include upper',exact=True).press('Tab')
            page.get_by_role('button',name='+ Add background band').click()
            page.get_by_label('include lower',exact=True).nth(1).fill('419')
            page.get_by_label('include upper',exact=True).nth(1).fill('435')
            page.get_by_label('include upper',exact=True).nth(1).press('Tab')
            page.get_by_role('status').filter(has_text='Recipe ready').wait_for()
            with page.expect_download() as info:
                page.get_by_role('button',name='Save recipe',exact=True).click()
            saved=tmp_path/'browser-recipe.json';info.value.save_as(saved)
            recipe=json.loads(saved.read_text())
            assert len(recipe['objects'])==2 and recipe['objects'][1]['spat']==397
            page.get_by_role('button',name='Reset to automatic').click()
            page.locator('#recipe-file').set_input_files(saved)
            page.get_by_role('status').filter(has_text='Saved recipe restored').wait_for()
            assert page.get_by_label('host Spatial pixel',exact=True).input_value()=='397'
            page.get_by_role('button',name='Extract & save revision').click()
            page.get_by_role('status').filter(has_text=re.compile('Revision saved|Extraction failed|Extraction cancelled|report plots need')).wait_for(timeout=90000)
            assert 'Revision saved' in page.get_by_role('status').inner_text(), page.locator('#log').inner_text()
            assert page.locator('#result option').count()==3
            page.get_by_role('button',name='FITS',exact=True).wait_for()
            with page.expect_download() as info:
                page.get_by_role('button',name='FITS',exact=True).click()
            product=tmp_path/'download.fits';info.value.save_as(product)
            assert fits.getdata(product).shape[0]==4
            page.get_by_label('Extraction',exact=True).select_option('boxcar')
            assert 'boxcar' in page.locator('#flux-note').inner_text()
            page.reload()
            page.get_by_role('status').filter(has_text='Revision saved').wait_for(timeout=30000)
            assert page.locator('#result option').count()==3
            assert errors==[]
            browser.close()
        replay=tmp_path/'cli-replay'
        reextract(run,'test_f.fits',recipe,replay,reference,render_report=False)
        result=Path(app.job_status()['directory'])
        for name in ('test_f.fits','test_obj_host_f.fits'):
            np.testing.assert_array_equal(fits.getdata(result/'products'/name),fits.getdata(replay/'products'/name))
    finally:
        server.shutdown();server.server_close();app.close();thread.join()


def test_detector_click_and_background_drag_save_native_coordinates(saved_exposure,tmp_path):
    playwright=pytest.importorskip('playwright.sync_api')
    from efospec.workbench import Workbench,create_server
    run,reference,_=saved_exposure
    app=Workbench(run,reference);server=create_server(app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with playwright.sync_playwright() as engine:
            kwargs={'headless':True}
            if os.environ.get('EFOSPEC_TEST_CHROME'):kwargs['executable_path']=os.environ['EFOSPEC_TEST_CHROME']
            browser=engine.chromium.launch(**kwargs)
            page=browser.new_page(viewport={'width':1440,'height':1200})
            page.goto(f'http://127.0.0.1:{server.server_port}/#{app.token}')
            page.get_by_role('status').filter(has_text='Original reduction loaded').wait_for()
            canvas=page.locator('#detector');canvas.scroll_into_view_if_needed();box=canvas.bounding_box()
            def point(spec,spat):
                return (box['x']+(83+(spec+.5)/160*(1074-83))*box['width']/1100,
                        box['y']+(292-(spat-298.5)/141*(292-16))*box['height']/340)
            page.mouse.click(*point(80,347))
            assert float(page.get_by_label('primary Spatial pixel',exact=True).input_value())==pytest.approx(347,abs=.3)
            page.get_by_label('Canvas tool',exact=True).select_option('include')
            for lo,hi in [(304,329),(419,435)]:
                page.mouse.move(*point(80,lo));page.mouse.down();page.mouse.move(*point(80,hi),steps=8);page.mouse.up()
            page.get_by_role('status').filter(has_text='Recipe ready').wait_for()
            with page.expect_download() as info:page.get_by_role('button',name='Save recipe',exact=True).click()
            saved=tmp_path/'clicked.json';info.value.save_as(saved);recipe=json.loads(saved.read_text())
            assert recipe['objects'][0]['spec']==pytest.approx(80,abs=.3)
            np.testing.assert_allclose(recipe['sky']['include'],[[304,329],[419,435]],atol=.3)
            browser.close()
    finally:
        server.shutdown();server.server_close();app.close();thread.join()
