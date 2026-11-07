"""A copied epoch page keeps its evidence and navigation without sibling files."""
import base64
from html.parser import HTMLParser
import json
from pathlib import Path

import pytest
from PIL import Image

from efospec.epoch_report import build_epoch_page
from efospec.inventory import sha256


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def epoch_page(tmp_path):
    root = tmp_path/'runs/2026-10-28'
    revision = root/'nightly/revision-1'
    run = revision/'reduction'
    save(root/'nightly/current.json', {'night':'2026-10-28', 'revision':'revision-1'})
    save(revision/'night.json', {'night':'2026-10-28', 'status':'partial', 'stages':{'reduce':{'status':'partial'}}})
    frame = {'path':'/raw/science.fits', 'role':'science', 'metadata':{'OBJECT':'SN <test>', 'DATE-OBS':'2026-10-29T02:00:00', 'EXPTIME':60},
             'setup':{'grism':'Gr13', 'filter':'Free', 'slit':'slit1.0'}}
    save(revision/'observing-log.json', {'frames':[frame]})
    product = run/'products/spectrum.fits';product.parent.mkdir(parents=True);product.write_bytes(b'saved spectrum\x00\x01')
    plots = run/'style-preview';plots.mkdir()
    images = []
    for prefix in ['FitSpectrum_', 'FitTrace_', 'FitSpatialProfile_']:
        image = plots/(prefix+'target.jpg');Image.new('RGB', (32, 24), '#244d3d').save(image);images.append(str(image))
    save(plots/'FitSpectrum_target.json', {'outputs':images, 'input_sha256':{str(product):sha256(product)}})
    save(run/'run.json', {'results':[{'raw':frame['path'], 'object':'SN <test>', 'product':str(product), 'grism':'Gr13'}],
        'errors':[{'path':'/raw/ambiguous.fits', 'object':'Ambiguous', 'code':'source_selection_required'}], 'skipped':[]})
    save(root/'archive/initial-reduction/run.json', {'results':[], 'errors':[{}], 'skipped':[{}]})
    return tmp_path, root, product


class Assets(HTMLParser):
    def __init__(self, html):
        super().__init__();self.ids=set();self.links=[];self.images=[];self.downloads={};self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:self.ids.add(a['id'])
        if tag=='a':
            self.links.append(a['href'])
            if 'download' in a:self.downloads[a['download']]=a['href']
        if tag=='img' and 'src' in a:self.images.append(a['src'])


def test_single_file_contains_evidence_downloads_and_only_internal_navigation(epoch_page):
    project, root, product = epoch_page
    before = {p:sha256(p) for p in root.rglob('*') if p.is_file()}
    result = build_epoch_page('2026-10-28', project)
    html = (root/'index.html').read_text();assets = Assets(html)
    assert result['embedded_figures']==3 and result['warnings']==[]
    assert 'SN &lt;test&gt;' in html and 'Target identity unverified' in html
    assert 'source_selection_required' in html and 'archive/initial-reduction' in html
    assert all(url.startswith(('data:', '#')) for url in assets.links+assets.images)
    assert all(url[1:] in assets.ids for url in assets.links if url.startswith('#'))
    assert base64.b64decode(assets.downloads[product.name].split(',',1)[1])==product.read_bytes()
    assert all(sha256(p)==digest for p,digest in before.items())


def test_stale_plot_hash_is_never_shown_as_current_spectrum(epoch_page):
    project, root, product = epoch_page
    product.write_bytes(b'changed reduction')
    result = build_epoch_page('2026-10-28', project)
    assert result['embedded_figures']==0
    assert 'figure unavailable' in (root/'index.html').read_text()


def test_transients_appear_before_standards_and_spectrum_links_keep_identity(epoch_page):
    from efospec.epoch_report import EpochPage
    project, root, product = epoch_page
    revision = root/'nightly/revision-1'
    run = json.loads((revision/'reduction/run.json').read_text())
    template = json.loads((revision/'observing-log.json').read_text())['frames'][0]
    frames, results = [], []
    for name, role in [('vma2','standard_candidate'), ('SN2026ayt','science'),
                       ('L745a','standard_candidate'), ('AT2026agzp','science')]:
        frames.append(dict(template, path=f'/raw/{name}.fits', role=role,
                           metadata=dict(template['metadata'], OBJECT=name)))
        results.append(dict(run['results'][0], raw=frames[-1]['path'], object=name))
    save(revision/'observing-log.json', {'frames':frames})
    run['results'] = results
    page = EpochPage(root)
    table = page.observations(revision, run)
    spectra = page.spectra(revision/'reduction', run)
    names = ['AT2026agzp','SN2026ayt','L745a','vma2']
    assert [table.index('<td>'+n+'</td>') for n in names] == sorted(table.index('<td>'+n+'</td>') for n in names)
    assert [spectra.index('id="spectrum-'+str(i)+'"') for i in [3,1,2,0]] == sorted(spectra.index('id="spectrum-'+str(i)+'"') for i in [3,1,2,0])
    for index, name in enumerate(['vma2','SN2026ayt','L745a','AT2026agzp']):
        row = next(row for row in table.split('<tr>') if '<td>'+name+'</td>' in row)
        assert f'href="#spectrum-{index}"' in row


def test_source_profiles_have_a_separate_full_width_card(epoch_page):
    project, root, _ = epoch_page
    packet = root/'nightly/revision-1/QC/ambiguous'
    save(packet/'review.json', {'object':'AT2026agzp', 'raw_name':'ambiguous.fits',
                               'identity':'UNVERIFIED', 'candidates':[]})
    for kind in ['science', 'traces', 'profiles', 'acquisition-1']:
        Image.new('RGB', (40, 10), 'white').save(packet/f'FitQC_AT2026agzp_{kind}.jpg')
    result = build_epoch_page('2026-10-28', project)
    html = (root/'index.html').read_text()
    assert result['embedded_figures'] == 7
    labels = ['2D Spectrum', 'Sky-subtracted 2D spectrum',
              'Spatial Profile and Trace Identification', 'Acquisition 1']
    positions = [html.index('<figcaption>AT2026agzp / '+label) for label in labels]
    assert positions == sorted(positions)
    assert '<figure class="plot full-width"><figcaption>AT2026agzp / Spatial Profile and Trace Identification' in html


def test_report_does_not_follow_a_different_nights_pointer(epoch_page):
    project, root, _ = epoch_page
    save(root/'nightly/current.json', {'night':'2026-10-28', 'revision':'../../2026-10-29'})
    with pytest.raises(ValueError, match='dated revision pointer'):
        build_epoch_page('2026-10-28', project)
    assert not (root/'index.html').exists()


def test_calibration_checks_order_transients_and_mark_failed_or_unvalidated(epoch_page):
    from efospec.epoch_report import EpochPage
    _,root,_=epoch_page
    run=root/'nightly/revision-1/reduction'
    for i,(name,status) in enumerate([('vma2','failed'),('SN2026aadx','passed'),
                                     ('AT2026twd','unvalidated'),('L745a','passed')]):
        save(run/f'checks/{i}/check.json',{'metadata':{'object':name},'status':status})
    html=EpochPage(root).wavelength_checks(run)
    names=['AT2026twd','SN2026aadx','L745a','vma2']
    assert [html.index(name) for name in names]==sorted(html.index(name) for name in names)
    assert html.count('class="qc-unvalidated"')==2
    assert 'Wavelength correction is not validated' in html


def test_calibration_table_uses_selected_manifest_outside_canonical_folder(epoch_page):
    from efospec.epoch_report import EpochPage
    _,root,_=epoch_page;revision=root/'nightly/revision-1'
    selected=root/'native-selected'
    save(selected/'run.json',{'groups':[{'id':'selected','setup':{'grism':'Gr16','filter':'OG530','slit':'slit1.5'},
                                       'status':'unvalidated','wave_qa':[]}]})
    state=json.loads((revision/'night.json').read_text());state['native_calibrations']=str(selected)
    save(revision/'night.json',state)
    html=EpochPage(root).calibrations(revision)
    assert 'Gr16' in html and 'qc-status-bad' in html


def test_background_is_bound_to_its_exposure_and_later_recipe_revision(epoch_page):
    project, root, _ = epoch_page
    packet = root/'QC/ambiguous'
    save(packet/'review.json', {'object':'SN with host', 'raw_name':'ambiguous.fits', 'identity':'UNVERIFIED',
        'input_sha256':{'raw':'correct'}, 'candidates':[{'number':3, 'anchor_raw_x':548.84}]})
    recipe = {'input_sha256':{'raw':'correct'}, 'objects':[{'label':'C3 provisional', 'spat':548.84}],
              'sky':{'degree':2, 'include':[[520,535],[555,575]]}}
    for folder, fraction in [('degree2', .8), ('degree2-v2', .928)]:
        save(packet/folder/'recipe.json', recipe)
        save(packet/folder/'background.json', {'valid_spectrum_fraction':fraction})
    wrong = dict(recipe, input_sha256={'raw':'different exposure'})
    save(packet/'unrelated/recipe.json', wrong)
    save(packet/'unrelated/background.json', {'valid_spectrum_fraction':.123})
    save(root/'QC/other/review.json', {'object':'Other epoch', 'raw_name':'other.fits'})
    build_epoch_page('2026-10-28', project)
    html = (root/'index.html').read_text()
    assert 'C3 provisional' in html and '[520, 535), [555, 575)' in html
    assert '92.8%' in html and '80.0%' not in html and '12.3%' not in html
    assert 'Other epoch' not in html


def test_copied_page_works_offline_with_zoom_navigation_and_download(epoch_page, tmp_path):
    from playwright.sync_api import sync_playwright
    project, root, product = epoch_page
    build_epoch_page('2026-10-28', project)
    standalone = tmp_path/'standalone.html';standalone.write_bytes((root/'index.html').read_bytes())
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(offline=True, accept_downloads=True)
        page = context.new_page();page.goto(standalone.as_uri())
        page.locator('.enlarge').first.scroll_into_view_if_needed()
        page.wait_for_function('Array.from(document.querySelectorAll(".enlarge img")).every(i => i.complete && i.naturalWidth > 0)')
        page.locator('.enlarge').first.click()
        assert page.locator('dialog').is_visible()
        page.get_by_role('button', name='Close', exact=True).click()
        page.get_by_role('link', name='Reduction Archive', exact=True).click()
        assert page.url.endswith('#archive')
        with page.expect_download() as download:
            page.get_by_role('link', name='FITS', exact=True).click()
        assert Path(download.value.path()).read_bytes()==product.read_bytes()
        page.set_viewport_size({'width':390, 'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        context.close();browser.close()


def test_local_background_geometry_is_not_reported_as_a_successful_reduction(epoch_page):
    project,root,_=epoch_page
    manifest=root/'nightly/revision-1/reduction/run.json'
    run=json.loads(manifest.read_text());run['results'][0]['raw_sha256']='a'*64
    save(manifest,run)
    directory=root/'QC/local-background-test/Target';directory.mkdir(parents=True)
    image=directory/'FitQC_target.jpg';Image.new('RGB',(32,24),'white').save(image)
    record={'night':'2026-10-28','parent_manifest_sha256':sha256(manifest),'mode':'geometry_preflight',
        'targets':[{'object':'Target','raw_name':'science.fits','input_sha256':{'raw':'a'*64},
          'figures':{image.name:sha256(image)},'cases':[{'candidate':1,'raw_x':548.,'width_pixels':40,
          'status':'insufficient_two_sided_space'}]}]}
    save(directory.parent/'local-background.json',record)
    result=build_epoch_page('2026-10-28',project)
    html=(root/'index.html').read_text()
    assert result['embedded_figures']==4
    assert 'Geometry checks only' in html and 'Insufficient two-sided space' in html
    image.write_bytes(b'changed')
    result=build_epoch_page('2026-10-28',project)
    assert result['embedded_figures']==3
    assert any('figure is missing or changed' in warning for warning in result['warnings'])
    record['parent_manifest_sha256']='b'*64
    save(directory.parent/'local-background.json',record)
    build_epoch_page('2026-10-28',project)
    assert 'Bounded background' not in (root/'index.html').read_text()
