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


def test_pending_response_counts_show_actual_stage_and_direct_anchor(epoch_page):
    from efospec.epoch_report import EpochPage
    project, root, product=epoch_page
    revision=root/'nightly/revision-1'; run=revision/'reduction'
    ascii_path=product.with_suffix('.asci');ascii_path.write_text('saved counts')
    record=dict(raw='/raw/science.fits',object='SN <test>',setup=dict(grism='Gr13',filter='GG495',slit='slit1.0'),
        product=str(product),ascii=str(ascii_path),product_sha256={str(product):sha256(product)},
        delivery_status='Counts extracted; flux calibration pending',
        pending_checks=['response selection: no matching physical reference'])
    manifest=dict(results=[],errors=[],skipped=[],review_counts=[record])
    page=EpochPage(root)
    html=page.spectra(run,manifest)+page.observations(revision,manifest)
    assert 'Counts extracted; flux calibration pending' in html
    assert 'no matching physical reference' in html and 'GG495' in html
    assert 'Wavelength validation failed' not in html
    assert 'id="spectrum-counts-0"' in html and 'href="#spectrum-counts-0"' in html
    assert 'efospec://review?' in html and 'Open in EFOSpec GUI' in html


def test_review_report_keeps_selected_page_and_pointer_unchanged(epoch_page):
    from efospec.epoch_report import build_epoch_page
    project, root, product=epoch_page
    build_epoch_page('2026-10-28', project)
    before={p:sha256(p) for p in (root/'index.html',root/'nightly/current.json',product)}
    revision=root/'nightly/revision-1'
    build_epoch_page('2026-10-28',project,revision_dir=revision)
    assert (revision/'index.html').exists()
    assert 'The selected nightly reduction is unchanged' in (revision/'index.html').read_text()
    assert all(sha256(p)==h for p,h in before.items())
    with pytest.raises(ValueError,match='belong to this observing night'):
        build_epoch_page('2026-10-28',project,revision_dir=project/'runs/2026-10-29/QC/other')


class Assets(HTMLParser):
    def __init__(self, html):
        super().__init__();self.ids=set();self.links=[];self.handoffs=[];self.images=[];self.downloads={};self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:self.ids.add(a['id'])
        if 'data-review-url' in a:self.handoffs.append(a['data-review-url'])
        if tag=='a':
            self.links.append(a['href'])
            if 'download' in a:self.downloads[a['download']]=a['href']
        if tag=='img' and 'src' in a:self.images.append(a['src'])


def test_iraf_supplement_is_separate_from_main_log(epoch_page,monkeypatch):
    from efospec import iraf_report
    from efospec.epoch_report import build_epoch_page
    project,root,_=epoch_page
    monkeypatch.setattr(iraf_report,'comparison_section',lambda page,revision:'<p>Unique overlay evidence</p>')
    build_epoch_page(root.name,project)
    main=(root/'index.html').read_text()
    supplement=(root/'iraf-comparison.html').read_text()
    assert 'href="iraf-comparison.html"' in main
    assert 'Unique overlay evidence' not in main
    assert 'Unique overlay evidence' in supplement
    assert 'href="index.html"' in supplement
    assert (root/'iraf-comparison-portable.html').is_file()


def test_old_high_snr_sky_failure_gets_precise_explanation_without_changing_record(tmp_path):
    from copy import deepcopy
    from efospec.epoch_report import EpochPage
    item=dict(object='SNtest',code='wavelength_validation_failed',
        error='sky line 6363.78 is weak or unconstrained (SNR 31.8, centroid error 3.33 A)',
        diagnostics={'lines':[dict(rest_air_angstrom=6363.776,peak_snr=31.8,
            centroid_error_angstrom=3.33,sigma_angstrom=11.95,
            profile='uniform_slit_convolved_gaussian')]})
    before=deepcopy(item)
    html=EpochPage(tmp_path).problems(dict(flux_calibration='same-night',errors=[item]),tmp_path)
    assert 'centroid uncertainty 3.33 A exceeds 1.50 A' in html
    assert 'peak/residual SNR 31.8; minimum 5' in html
    assert 'weak or unconstrained' not in html
    assert item==before


def test_single_file_contains_evidence_downloads_and_only_internal_navigation(epoch_page):
    project, root, product = epoch_page
    before = {p:sha256(p) for p in root.rglob('*') if p.is_file()}
    result = build_epoch_page('2026-10-28', project)
    html = (root/'index-portable.html').read_text();assets = Assets(html)
    assert result['embedded_figures']==3 and result['warnings']==[]
    assert 'SN &lt;test&gt;' in html and 'Target identity unverified' in html
    assert 'source_selection_required' in html and 'archive/initial-reduction' in html
    assert all(url.startswith(('data:', '#', 'efospec://review?')) for url in assets.links+assets.images)
    assert all(url[1:] in assets.ids for url in assets.links if url.startswith('#'))
    assert base64.b64decode(assets.downloads[product.name].split(',',1)[1])==product.read_bytes()
    assert all(sha256(p)==digest for p,digest in before.items())


def test_stale_plot_hash_is_never_shown_as_current_spectrum(epoch_page):
    project, root, product = epoch_page
    product.write_bytes(b'changed reduction')
    result = build_epoch_page('2026-10-28', project)
    assert result['embedded_figures']==0
    assert 'figure unavailable' in (root/'index.html').read_text()


@pytest.mark.parametrize('mode', ['current','stale','accepted'])
def test_rescue_report_keeps_failed_wavelength_status_and_parent_identity(epoch_page,mode):
    project,root,product=epoch_page
    parent=root/'nightly/revision-1/reduction/run.json'
    original=json.loads(parent.read_text())
    raw='/raw/science.fits' if mode=='accepted' else '/raw/failed-wave.fits'
    original['errors'].append(dict(path='/raw/failed-wave.fits',object='Failed wave',code='wavelength_validation_failed'))
    save(parent,original)
    rescue=root/'rescue/trial'
    spectrum=rescue/'provisional.fits';spectrum.parent.mkdir(parents=True);spectrum.write_bytes(b'provisional')
    run=dict(night='2026-10-28',parent_sha256='stale' if mode=='stale' else sha256(parent),
        wavelength_policy='provisional_arc_only',results=[dict(raw=raw,object='Failed wave',grism='Gr11',
            product=str(spectrum),product_sha256={str(spectrum):sha256(spectrum)},status='PROVISIONAL',
            wavelength_validated=False,interpretation='Selected trace; identity unverified.')])
    save(rescue/'run.json',run)
    save(root/'rescue/current.json',dict(night='2026-10-28',path='rescue/trial',run_sha256=sha256(rescue/'run.json')))
    before=sha256(parent)
    if mode=='accepted':
        with pytest.raises(ValueError,match='cannot replace an accepted product'):
            build_epoch_page('2026-10-28',project)
    else:
        result=build_epoch_page('2026-10-28',project)
        html=(root/'index.html').read_text()
        if mode=='current':
            assert 'id="rescue-spectrum-0"' in html
            assert 'science wavelengths remain unvalidated' in html
            assert 'id="spectrum-0"' in html
        else:
            assert 'id="rescue-spectrum-0"' not in html
            assert 'Retained provisional rescue belongs' not in html
    assert sha256(parent)==before and product.read_bytes()==b'saved spectrum\x00\x01'


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
    for kind in ['science', 'traces', 'profiles', 'acquisition-1', 'acquisition-2']:
        Image.new('RGB', (40, 10), 'white').save(packet/f'FitQC_AT2026agzp_{kind}.jpg')
    result = build_epoch_page('2026-10-28', project)
    html = (root/'index.html').read_text()
    assert result['embedded_figures'] == 8
    labels = ['2D Spectrum', 'Sky-subtracted 2D spectrum',
              'Spatial Profile and Trace Identification', 'Acquisition 1', 'Acquisition 2']
    positions = [html.index('<figcaption>AT2026agzp / '+label) for label in labels]
    assert positions == sorted(positions)
    assert '<figure class="plot full-width"><figcaption>AT2026agzp / Spatial Profile and Trace Identification' in html
    profile_card=html[positions[2]:positions[3]]
    assert 'style="aspect-ratio:2"' not in profile_card
    assert 'object-fit:contain' in html


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
    standalone = tmp_path/'standalone.html';standalone.write_bytes((root/'index-portable.html').read_bytes())
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


def test_daily_response_provenance_download_and_tamper_check(epoch_page):
    project,root,product=epoch_page
    manifest=root/'nightly/revision-1/reduction/run.json'
    run=json.loads(manifest.read_text())
    response=manifest.parent/'response.fits';response.write_bytes(b'new response')
    run['flux_calibration']='same-night'
    run['results'][0]['sensitivity']=dict(standard_name='VMa2',standard_raw='/raw/today.fits')
    run['standards']=[dict(frame=dict(path='/raw/today.fits',metadata={'OBJECT':'VMa2','DATE-OBS':'2026-10-29T03:00'},
        setup=dict(grism='Gr13',filter='Free',slit='slit1.0')),
        fit=dict(status='response_built_unvalidated',response=dict(path=str(response),sha256=sha256(response))))]
    save(manifest,run)
    build_epoch_page('2026-10-28',project)
    html=(root/'index.html').read_text(); assets=Assets(html)
    assert 'Same-night standard responses' in html and 'today.fits' in html
    assert 'absolute accuracy unvalidated' in html
    assert '0 held-out exposure transfers' in html
    assert (root/assets.downloads['response.fits']).read_bytes()==response.read_bytes()
    response.write_bytes(b'changed')
    with pytest.raises(ValueError,match='daily response changed'):
        build_epoch_page('2026-10-28',project)


def test_log_stage_with_retained_rescue_does_not_require_new_reduction_manifest(epoch_page):
    project,root,product=epoch_page
    parent=root/'nightly/revision-1/reduction/run.json'
    rescue=root/'rescue/earlier'
    save(rescue/'run.json',dict(night='2026-10-28',parent_sha256=sha256(parent),
        wavelength_policy='provisional_arc_only',results=[]))
    save(root/'rescue/current.json',dict(night='2026-10-28',path='rescue/earlier',
        run_sha256=sha256(rescue/'run.json')))
    parent.unlink()
    before=sha256(product)
    result=build_epoch_page('2026-10-28',project)
    html=(root/'index.html').read_text()
    assert 'Retained provisional rescue belongs' not in html
    assert 'Provisional rescue spectra' not in html
    assert sha256(product)==before
    assert not parent.exists()


def test_failed_and_skipped_exposures_keep_target_reason_log_and_handoff(epoch_page):
    from efospec.review_handoff import parse_review_url
    project,root,_=epoch_page
    run=root/'nightly/revision-1/reduction'
    manifest=json.loads((run/'run.json').read_text())
    log=run/'failure.log';log.write_text('saved traceback <unaltered>')
    item=dict(object='SN <failed>',path='/raw/failed.fits',code='background_support_required',
              error='Final trace crosses band',traceback=str(log),setup={'grism':'Gr13'})
    manifest['errors']=[item]
    manifest['skipped']=[dict(object='SN <failed>',path='/raw/red.fits',code='unsupported_setup',reason='Gr16 unsupported')]
    save(run/'run.json',manifest)
    before=sha256(run/'run.json')
    build_epoch_page(root.name,project)
    html=(root/'index-portable.html').read_text();assets=Assets(html)
    assert '<h3>SN &lt;failed&gt; · Gr13</h3><p class="qc-status-bad">background_support_required: Final trace crosses band' in html
    links=[parse_review_url(url) for url in assets.handoffs]
    assert links==[(str(run),'failed.fits'),(str(run),'red.fits')]
    assert {'spectrum-errors-0','spectrum-skipped-0'} <= assets.ids
    assert base64.b64decode(assets.downloads[log.name].split(',',1)[1])==log.read_bytes()
    assert sha256(run/'run.json')==before


def test_detailed_failure_is_only_in_source_logs_and_headings_include_seconds(epoch_page):
    project,root,_=epoch_page
    run=root/'nightly/revision-1/reduction';path=run/'run.json'
    manifest=json.loads(path.read_text())
    manifest['errors']=[dict(object='SN <test>',path='/raw/science.fits',
        code='wavelength_validation_failed',error='native sky anchors disagree by more than 3 A')]
    save(path,manifest)
    build_epoch_page(root.name,project)
    html=(root/'index.html').read_text()
    observations=html.split('id="observations"')[1].split('</section>')[0]
    spectra=html.split('id="spectra"')[1].split('</section>')[0]
    assert 'native sky anchors disagree' not in observations
    assert 'native sky anchors disagree' in spectra
    assert '<h3>SN &lt;test&gt; · Gr13 · 60 s</h3>' in spectra
    assert '<h3>SN &lt;test&gt; · 60 s</h3>' in spectra
    assert '<button type="button" class="review-launch"' in spectra
    assert '<a class="review-launch"' not in spectra
