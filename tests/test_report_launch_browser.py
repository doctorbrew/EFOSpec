"""Desktop launch failure must leave the read-only log visible."""
import pytest
from test_epoch_report import epoch_page
from efospec.epoch_report import build_epoch_page


@pytest.mark.parametrize('embedded', [False, True])
def test_desktop_button_keeps_report_and_exposes_fallback(epoch_page,embedded):
    playwright=pytest.importorskip('playwright.sync_api')
    project,root,_=epoch_page
    build_epoch_page(root.name,project)
    with playwright.sync_playwright() as pw:
        browser=pw.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':900})
        if embedded:page.set_content((root/'index.html').read_text())
        else:page.goto((root/'index.html').as_uri())
        original_url=page.url
        page.locator('.review-launch').click()
        assert page.url==original_url
        assert page.locator('h1').inner_text()==root.name
        assert page.locator('.review-help').get_attribute('open') is not None
        assert 'efospec gui' in page.locator('.review-help pre').inner_text()
        assert 'Desktop launch requested' in page.locator('.launch-status').inner_text()
        assert page.locator('#desktop-launch-bridge').count()==1
        assert len(page.context.pages)==1
        assert page.locator('#spectra .exposure').nth(1).evaluate('(el)=>getComputedStyle(el).borderTopStyle')=='solid'
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        browser.close()
