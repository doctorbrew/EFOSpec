"""Comparison flux outside the native range must remain visible."""
import numpy as np
import pytest


@pytest.mark.parametrize('legacy_flux', [10., -8.])
def test_spectrum_limits_include_both_curves(legacy_flux):
    from scripts.preview_spectrum_style import draw_spectrum
    import matplotlib.pyplot as plt
    wave=np.linspace(4000,8000,40)
    bands=np.ones((4,40))*1e-16;bands[3]*=.1
    old=bands.copy();old[0]=legacy_flux*1e-16
    result=dict(object='SNtest',grism='Gr13',exptime_s=300.,product='test.fits',
                median_native_snr_4000_8500=10.)
    fig,ax=plt.subplots()
    try:
        draw_spectrum(ax,result,wave,bands,{'path':'legacy.fits'},(wave,old))
        low,high=ax.get_ylim()
        assert low < legacy_flux < high
        assert low < .9 < 1.1 < high
        assert ax.title.get_fontsize()==28
    finally:
        plt.close(fig)
