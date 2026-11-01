"""Independent sky-line validation of a native arc wavelength solution."""
import numpy as np
from scipy.optimize import curve_fit


def measure_flexure(data,waveair):
    """Two offset anchors, then a genuinely isolated 6363-A validation window."""
    data,waveair=np.asarray(data,float),np.asarray(waveair,float)
    if data.ndim!=2 or data.shape!=waveair.shape or data.shape[1]<40:
        raise ValueError('sky validation requires a two-dimensional long-slit window')
    wave=waveair[:,waveair.shape[1]//2]
    if not np.all(np.diff(waveair,axis=0)>0):raise ValueError('sky wavelength map must increase')
    columns=np.arange(10,data.shape[1]-10,3)
    sky=np.nanmedian([np.interp(wave,waveair[:,col],data[:,col]) for col in columns],axis=0)
    def gaussian(w,a,center,sigma,b,slope):
        return a*np.exp(-.5*((w-center)/sigma)**2)+b+slope*(w-center)
    lines=[];shift=0.
    for rest in (5577.338,6300.304,6363.776):
        expected=rest-shift
        keep=(abs(wave-expected)<28)&np.isfinite(sky)
        w,f=wave[keep],sky[keep]
        if len(w)<9:raise ValueError(f'insufficient spectral coverage for sky line {rest:g}')
        base=float(np.median(np.r_[f[:2],f[-2:]]))
        guess=[max(float(f.max()-base),1.),float(w[f.argmax()]),7.5,base,0.]
        try:
            p,cov=curve_fit(gaussian,w,f,p0=guess,bounds=([0,expected-20,3,-np.inf,-np.inf],
                    [np.inf,expected+20,14,np.inf,np.inf]),maxfev=10000)
        except (RuntimeError,ValueError) as exc:
            raise ValueError(f'cannot fit isolated sky line {rest:g}') from exc
        residual=f-gaussian(w,*p)
        noise=max(1.4826*np.median(abs(residual-np.median(residual))),1e-6)
        snr=float(p[0]/noise);error=float(np.sqrt(max(cov[1,1],0)))
        if snr<(5 if rest==6363.776 else 8) or not np.isfinite(error) or error>1.5 or not 3.1<p[2]<13.9:
            raise ValueError(f'sky line {rest:g} is weak or unconstrained (SNR {snr:.1f}, centroid error {error:.2f} A)')
        lines.append(dict(rest_air_angstrom=rest,measured_air_angstrom=float(p[1]),
            offset_angstrom=float(rest-p[1]),peak_snr=snr,sigma_angstrom=float(p[2]),
            centroid_error_angstrom=error))
        if rest==6300.304:
            if abs(lines[0]['offset_angstrom']-lines[1]['offset_angstrom'])>3:
                raise ValueError('native sky anchors disagree by more than 3 A')
            shift=float(np.mean([line['offset_angstrom'] for line in lines]))
            if abs(shift)>20:raise ValueError('native sky shift exceeds 20 A')
    for line in lines:line['residual_after_shift_angstrom']=line['measured_air_angstrom']+shift-line['rest_air_angstrom']
    residual=lines[2]['residual_after_shift_angstrom']
    if abs(residual)>3:raise ValueError(f'independent 6363-A residual is {residual:.2f} A')
    return shift,dict(shift_angstrom=shift,lines=lines,held_out_6363_residual_angstrom=residual,
                      held_out_6363_pass=True,policy='isolated 5577/6300 fits and held-out 6363 validation')
