"""Before/after presentation must never cross reduction revisions or lose data."""
import base64
import json
from pathlib import Path
import shutil

import numpy as np
import pytest
from astropy.io import fits

from efospec.inventory import sha256
from efospec.telluric_products import select_for_report,selected_pairs,read_overlay,overlay_record


@pytest.fixture
def paired_run(tmp_path):
    root=tmp_path/'runs/2026-10-28';run=root/'nightly/v1/reduction';revision=root/'QC/telluric-v1'
    (run/'products').mkdir(parents=True);(revision/'products').mkdir(parents=True);(revision/'uncorrected').mkdir()
    source=run/'products/transient.fits';after=revision/'products'/source.name;before=revision/'uncorrected'/source.name
    data=np.ones((4,1,5))*1e-16;mask=np.ones((1,5),np.uint8)
    header=fits.Header({'CRVAL1':7600.,'CD1_1':5.,'CRPIX1':2.,'WAVEMED':'air','BUNIT':'erg/cm2/s/Angstrom'})
    fits.HDUList([fits.PrimaryHDU(data,header),fits.ImageHDU(mask,name='VALID')]).writeto(source,checksum=True)
    shutil.copyfile(source,before)
    header['TELVALID']='REVIEW';corrected=data.copy();corrected[0]*=2
    table=fits.BinTableHDU.from_columns([fits.Column(name='APPLIED',format='L',array=np.ones(5,bool)),
        fits.Column(name='ORIGINAL_VALID',format='L',array=np.ones(5,bool))],name='TELLURIC')
    fits.HDUList([fits.PrimaryHDU(corrected,header),fits.ImageHDU(mask,name='VALID'),
                  fits.ImageHDU(data,name='UNCORRECTED'),table]).writeto(after,checksum=True)
    before.with_suffix('.asci').write_text('before data\n');after.with_suffix('.asci').write_text('after data\n')
    result=dict(product=str(source),role='science',raw='/raw/transient.fits',raw_sha256='abc',object='SNtest',
                grism='Gr13',exptime_s=300.,median_native_snr_4000_8500=10.)
    (run/'run.json').write_text(json.dumps(dict(night=root.name,results=[result],errors=[],skipped=[])))
    row=dict(raw=result['raw'],raw_sha256='abc',source_product=str(source),source_sha256=sha256(source),
        product=str(after),sha256=sha256(after),uncorrected_product=str(before),uncorrected_sha256=sha256(before),
        ascii=str(after.with_suffix('.asci')),ascii_sha256=sha256(after.with_suffix('.asci')),
        uncorrected_ascii=str(before.with_suffix('.asci')),uncorrected_ascii_sha256=sha256(before.with_suffix('.asci')),
        bands=['O2_A'],status='review_required_transfer',review_reasons=['airmass outside tested range'])
    manifest=revision/'run.json';manifest.write_text(json.dumps(dict(status='complete',night=root.name,
        source_run=str(run/'run.json'),source_run_sha256=sha256(run/'run.json'),products=[row])))
    return root,run,manifest


def test_selection_binds_exact_parent_and_preserves_both_masks(paired_run):
    root,run,manifest=paired_run
    select_for_report(run,manifest);pair=selected_pairs(run)['transient.fits'];data=read_overlay(pair)
    np.testing.assert_array_equal(data['wave'],[7595.,7600.,7605.,7610.,7615.])
    assert data['review'] and data['original_valid'].all() and data['applied'].all()
    changed=json.loads((run/'run.json').read_text());changed['different_extraction']=True
    (run/'run.json').write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='different reduction revision'):selected_pairs(run)


def test_changed_pair_and_changed_manifest_are_rejected(paired_run):
    root,run,manifest=paired_run;select_for_report(run,manifest)
    pair=selected_pairs(run)['transient.fits'];Path(pair['ascii']).write_text('stale content')
    with pytest.raises(ValueError,match='pair file changed'):selected_pairs(run)
    manifest.write_text(manifest.read_text()+'\n')
    with pytest.raises(ValueError,match='manifest changed'):selected_pairs(run)


def test_reselection_preserves_the_previous_pointer_and_both_spectra(paired_run):
    root,run,manifest=paired_run
    pointer=select_for_report(run,manifest)
    original=pointer.read_bytes();digest=sha256(pointer)
    pair=selected_pairs(run)['transient.fits']
    protected={Path(pair[key]):sha256(Path(pair[key]))
               for key in ('source_product','product','uncorrected_product')}
    select_for_report(run,manifest)
    assert (run/'telluric-selections'/f'{digest}.json').read_bytes()==original
    assert all(sha256(path)==value for path,value in protected.items())


@pytest.mark.parametrize('fault,message',[
    ('units','flux units differ'),('original','preserve the original'),
    ('mask','validity masks'),('status','validation status')])
def test_overlay_rejects_inconsistent_scientific_content(paired_run,fault,message):
    root,run,manifest=paired_run
    select_for_report(run,manifest);pair=selected_pairs(run)['transient.fits']
    with fits.open(pair['product'],mode='update') as hdus:
        if fault=='units':hdus[0].header['BUNIT']='counts'
        elif fault=='original':hdus['UNCORRECTED'].data[0,0,0]*=2
        elif fault=='mask':hdus['VALID'].data[0,0]=0
        else:hdus[0].header['TELVALID']='UNVERIFIED'
    with pytest.raises(ValueError,match=message):read_overlay(pair)


def test_portable_report_has_distinct_exact_before_after_downloads(paired_run):
    from html.parser import HTMLParser
    from efospec.epoch_report import EpochPage
    root,run,manifest=paired_run;select_for_report(run,manifest)
    html=EpochPage(root).spectra(run,json.loads((run/'run.json').read_text()))
    class Downloads(HTMLParser):
        def __init__(self):super().__init__();self.files={}
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='a' and 'download' in a:self.files[a['download']]=base64.b64decode(a['href'].split(',',1)[1])
    parser=Downloads();parser.feed(html)
    pair=selected_pairs(run)['transient.fits']
    assert parser.files['transient_before_telluric.fits']==Path(pair['uncorrected_product']).read_bytes()
    assert parser.files['transient_after_telluric.fits']==Path(pair['product']).read_bytes()
    assert len(parser.files)==4 and 'airmass outside tested range' in html
    assert 'Before/after telluric plot has not been generated' in html


def test_comparison_plot_requires_both_current_products_and_figure_hashes(paired_run):
    from PIL import Image
    root,run,manifest=paired_run;select_for_report(run,manifest);pair=selected_pairs(run)['transient.fits']
    directory=Path(pair['plots_dir']);directory.mkdir();figure=directory/'FitSpectrum_SNtest.jpg'
    Image.new('RGB',(24,24),'white').save(figure)
    record=dict(telluric_pair=pair,outputs=[str(figure)],output_sha256={str(figure):sha256(figure)},
        input_sha256={pair['source_product']:pair['source_sha256'],pair['product']:pair['sha256'],
                      pair['manifest']:pair['manifest_sha256']})
    path=directory/'FitSpectrum_SNtest.json';path.write_text(json.dumps(record))
    assert overlay_record(pair)['outputs']==[str(figure)]
    record['input_sha256'][pair['product']]='stale';path.write_text(json.dumps(record))
    with pytest.raises(ValueError,match='stale inputs'):overlay_record(pair)


def test_telluric_curve_and_uncertainty_set_plot_limits():
    from scripts.preview_spectrum_style import draw_spectrum
    import matplotlib.pyplot as plt
    wave=np.linspace(6000,8500,50);bands=np.ones((4,50))*1e-16
    corrected=bands.copy();corrected[0]*=20;corrected[3]*=10
    overlay=dict(bands=corrected,applied=np.ones(50,bool),qualified_bands=['O2_A'],review=True)
    result=dict(object='SNtest',grism='Gr13',exptime_s=300.,product='test.fits',median_native_snr_4000_8500=10.)
    fig,ax=plt.subplots()
    try:
        draw_spectrum(ax,result,wave,bands,telluric=overlay)
        assert ax.get_ylim()[1]>30
        labels=ax.get_legend_handles_labels()[1]
        assert 'Before telluric' in labels and 'After telluric (review)' in labels
        corrected_line=next(line for line in ax.lines if line.get_label()=='After telluric (review)')
        np.testing.assert_array_equal(corrected_line.get_ydata(),corrected[0]/1e-16)
    finally:plt.close(fig)
