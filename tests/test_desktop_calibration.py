"""Calibration views preserve saved models, masks, units and input identity."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from astropy.io import fits
from matplotlib.figure import Figure
from efospec.inventory import sha256
from efospec.desktop_calibration import read_arc,read_response,draw_response,CalibrationView


def response_file(tmp_path):
    path=tmp_path/'response.fits'
    columns=[fits.Column(name=name,format=fmt,array=value) for name,fmt,value in [
        ('WAVE','D',[4000,5000,6000,7000,8000]),('ZEROPOINT','D',[20,21,22,21,20]),
        ('MEASURED_ZEROPOINT','D',[20.01,21.02,22.03,21.04,20.05]),
        ('VALID','L',[True,True,False,True,True]),('FIT_ACCEPTED','L',[True,True,False,True,False])]]
    fits.HDUList([fits.PrimaryHDU(header=fits.Header(dict(STDNAME='test',WAVEMED='vacuum'))),
                  fits.BinTableHDU.from_columns(columns,name='RESPONSE')]).writeto(path)
    return dict(path=str(path),sha256=sha256(path))


def test_response_plot_preserves_unsupported_gaps_and_saved_fit(tmp_path):
    record=response_file(tmp_path);before=sha256(Path(record['path']));data=read_response(record)
    assert np.isnan(data['factor'][2])
    np.testing.assert_array_equal(data['fit'],[20,21,22,21,20])
    fig=Figure();draw_response(fig,data)
    # The saved-fit line and physical response both break at the unsupported bin.
    assert np.isnan(fig.axes[0].lines[-1].get_ydata()[2])
    assert np.isnan(fig.axes[1].lines[0].get_ydata()[2])
    np.testing.assert_allclose(fig.axes[2].lines[0].get_ydata(),[.01,.02,.04])
    assert 'vacuum' in fig.axes[1].get_xlabel()
    assert sha256(Path(record['path']))==before
    record['sha256']='changed'
    with pytest.raises(ValueError,match='checksum'):read_response(record)


def test_arc_residuals_use_stored_solution_not_a_refit(tmp_path,monkeypatch):
    from pypeit.wavecalib import WaveCalib
    path=tmp_path/'WaveCalib_A.fits';path.write_bytes(b'saved model')
    (tmp_path/'calibration.json').write_text(json.dumps(dict(processed_files={path.name:sha256(path)})))
    model=SimpleNamespace(gpm=[True,True],eval=lambda x:4000+1000*np.asarray(x))
    fit=SimpleNamespace(pixel_fit=[1.,8.],wave_fit=[4101.,4798.],xnorm=10.,spec=np.ones(11),pypeitfit=model)
    monkeypatch.setattr(WaveCalib,'from_file',lambda path:SimpleNamespace(wv_fits=[fit]))
    data=read_arc(tmp_path)
    np.testing.assert_allclose(data['residual'],[-1.,2.])
    np.testing.assert_allclose(data['model'],np.arange(4000,5001,100))
    path.write_bytes(b'changed model')
    with pytest.raises(ValueError,match='checksum'):read_arc(tmp_path)


def test_missing_diagnostic_clears_previous_plot(qtbot,tmp_path):
    view=CalibrationView('flux','ATtest');qtbot.addWidget(view)
    assert view.load(response_file(tmp_path)) is None
    assert view.data is not None and view.export.isEnabled()
    assert view.load(None) is not None
    assert view.data is None and not view.export.isEnabled() and not view.figure.axes
