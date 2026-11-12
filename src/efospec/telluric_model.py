"""Native-sample fits of PypeIt's atmospheric PCA with marginal covariance.

This is a project fitting wrapper around PypeIt's radiative-transfer model, not
the pypeit_tellfit command. Data are never upsampled to the atmospheric grid.
"""
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.integrate import cumulative_trapezoid

MODEL = 'TellPCA_3000_26000_R10000.fits'
# Air-A evaluation/correction intervals include low-resolution band wings.
BANDS = {'O2_B':(6820.,7000.),'H2O_7200':(7120.,7390.),
         'O2_A':(7540.,7790.),'H2O_8200':(8090.,8310.)}


def pixel_edges(wave):
    wave=np.asarray(wave,float)
    if wave.ndim!=1 or len(wave)<2 or not np.isfinite(wave).all() or np.any(np.diff(wave)<=0):
        raise ValueError('telluric input requires a finite increasing one-dimensional wavelength grid')
    mid=(wave[1:]+wave[:-1])/2
    return np.r_[wave[0]-(mid[0]-wave[0]),mid,wave[-1]+(wave[-1]-mid[-1])]


class Atmosphere:
    def __init__(self, filename=MODEL, *, npca=2, lower=6000., upper=9000.):
        from pypeit import dataPaths
        from pypeit.core.telluric import read_telluric_pca
        from .inventory import sha256
        self.path=Path(dataPaths.telgrid.get_file_path(str(filename)))
        self.sha256=sha256(self.path)
        self.grid=read_telluric_pca(str(self.path),lower,upper)
        self.wave=self.grid['wave_grid'][1:-1]
        self.npca=npca;self.lower=lower;self.upper=upper
        if not 1<=npca<=self.grid['ncomp_tell_pca']:raise ValueError('invalid atmospheric PCA count')

    def evaluate(self, wave, theta, *, airmass_scale=1.):
        """theta = PCA coefficients, resolving power, offset in vacuum Angstrom."""
        from pypeit.core.telluric import eval_telluric, conv_telluric
        theta=np.asarray(theta,float);edges=pixel_edges(wave)-theta[-1]
        if edges[0]<self.wave[0] or edges[-1]>self.wave[-1]:
            raise ValueError('cannot extrapolate the atmospheric model')
        if not np.isfinite(airmass_scale) or airmass_scale<=0:raise ValueError('invalid airmass ratio')
        if airmass_scale==1.:
            model=eval_telluric(np.r_[theta[:self.npca],theta[-2],0.,1.],self.grid,
                ind_lower=1,ind_upper=len(self.grid['wave_grid'])-2)
        else:
            # Scale physical optical depth BEFORE instrumental convolution.
            # Raising an already blurred transmission to an airmass ratio is wrong.
            tau=np.maximum(np.sinh(np.r_[1.,theta[:self.npca]]@self.grid['tell_pca'][:self.npca+1]),0.)
            model=conv_telluric(np.exp(-tau*airmass_scale),self.grid['dloglam'],theta[-2])[1:-1]
        integral=cumulative_trapezoid(model,self.wave,initial=0.)
        return np.diff(np.interp(edges,self.wave,integral))/np.diff(edges)

    def bounds(self, resolution, fractions=(.5,2.), shift_limit=15.):
        bounds=self.grid['bounds_tell_pca'][:,1:self.npca+1]
        return np.r_[bounds[0],resolution*fractions[0],-shift_limit],np.r_[bounds[1],resolution*fractions[1],shift_limit]


def continuum_basis(wave,lower,upper,degree):
    return np.polynomial.legendre.legvander(2*(np.asarray(wave)-lower)/(upper-lower)-1,degree)


def fit_standard(atmosphere,wave,ratio,sigma,valid,*,resolution=400.,polyorder=3,sn_clip=30.,seed=777,
                 resolution_bounds=(.5,2.)):
    """Fit known stellar flux times smooth residual throughput and atmosphere.

    The caller removes stellar features, NOT atmospheric bands. An S/N ceiling
    limits leverage from reference/response imperfections. Local covariance is
    retained in full; independent-transfer residuals must supplement it.
    """
    wave=np.asarray(wave,float);pixel_edges(wave)
    ratio,sigma=np.asarray(ratio,float),np.asarray(sigma,float)
    valid=np.asarray(valid,bool)&np.isfinite(ratio)&np.isfinite(sigma)&(sigma>0)&(ratio>0)
    valid&=(wave>=atmosphere.lower)&(wave<=atmosphere.upper)
    if valid.sum()<80:raise ValueError('insufficient standard coverage for atmospheric fit')
    # Retain the full native grid in evaluations so masking never changes pixel widths.
    use=(wave>=atmosphere.lower)&(wave<=atmosphere.upper)
    w=wave[use];r=ratio[use];s=sigma[use];g=valid[use]
    s=np.maximum(s,np.abs(r)/sn_clip)
    basis=continuum_basis(w,atmosphere.lower,atmosphere.upper,polyorder)
    alo,ahi=atmosphere.bounds(resolution,resolution_bounds)
    lo=np.r_[alo,[-2.]*(polyorder+1)];hi=np.r_[ahi,[2.]*(polyorder+1)]
    mid=(lo+hi)/2;scale=(hi-lo)/2
    def model(q):
        p=mid+scale*q
        return atmosphere.evaluate(w,p[:atmosphere.npca+2])*np.exp(basis@p[atmosphere.npca+2:])
    def residual(q):return ((model(q)-r)/s)[g]
    initial=np.r_[np.zeros(atmosphere.npca),resolution,0.,np.log(np.median(r[g])),np.zeros(polyorder)]
    rng=np.random.default_rng(seed);solutions=[]
    for i in range(3):
        start=(initial-mid)/scale if i==0 else np.clip((initial-mid)/scale+rng.normal(0,.08,len(mid)),-.95,.95)
        solutions.append(least_squares(residual,np.clip(start,-.99,.99),bounds=(-1,1),
            diff_step=1e-4,max_nfev=400,ftol=1e-8,xtol=1e-8,gtol=1e-7))
    opt=min(solutions,key=lambda x:np.sum(x.fun**2))
    if not opt.success:raise ValueError('atmospheric fit did not converge')
    sv=np.linalg.svd(opt.jac,compute_uv=False)
    if sv[-1]<sv[0]*1e-7:raise ValueError('atmospheric fit is rank deficient')
    if np.any(abs(opt.x)>.995):
        raise ValueError(f'atmospheric fit reached a parameter bound: indices {np.flatnonzero(abs(opt.x)>.995).tolist()}, values {(mid+scale*opt.x).tolist()}')
    redchi=float(np.sum(opt.fun**2)/(g.sum()-len(mid)))
    covq=np.linalg.inv(opt.jac.T@opt.jac)*max(1.,redchi)
    cov=covq*scale[:,None]*scale[None,:];p=mid+scale*opt.x
    t=atmosphere.evaluate(w,p[:atmosphere.npca+2])
    return dict(theta=p.tolist(),covariance=cov.tolist(),npca=atmosphere.npca,polyorder=polyorder,
        resolution=float(p[atmosphere.npca]),shift_vacuum_angstrom=float(p[atmosphere.npca+1]),
        reduced_chi2=redchi,fit_samples=int(g.sum()),condition_number=float(sv[0]/sv[-1]),
        model_file=str(atmosphere.path),model_sha256=atmosphere.sha256,
        fit_range_vacuum_angstrom=[atmosphere.lower,atmosphere.upper],sn_clip=sn_clip,
        uncertainty='Local joint-fit covariance, scaled up for reduced chi-square; not temporal/model uncertainty.'),dict(
        wave=w,ratio=r,sigma=s,valid=g,transmission=t,continuum=np.exp(basis@p[atmosphere.npca+2:]))


def predict(atmosphere,wave,record,*,shift=None,resolution=None,airmass_scale=1.,shift_sigma=0.,resolution_sigma=0.,return_details=False):
    """Transmission and marginal variance; covariance remains in the fit record."""
    n=atmosphere.npca+2;p=np.array(record['theta'][:n]);cov=np.array(record['covariance'])[:n,:n]
    # An independently determined science wavelength offset replaces the raw
    # standard's offset and its correlations; retain marginal PCA uncertainties.
    if shift is not None:
        p[-1]=shift;cov[-1,:]=0.;cov[:,-1]=0.
    if resolution is not None:
        p[-2]=resolution;cov[-2,:]=0.;cov[:,-2]=0.
    cov[-1,-1]+=shift_sigma**2;cov[-2,-2]+=resolution_sigma**2
    t=atmosphere.evaluate(wave,p,airmass_scale=airmass_scale);jac=[]
    for i in range(n):
        step=max(abs(p[i])*1e-4,1e-3);a=p.copy();b=p.copy();a[i]+=step;b[i]-=step
        jac.append((atmosphere.evaluate(wave,a,airmass_scale=airmass_scale)-atmosphere.evaluate(wave,b,airmass_scale=airmass_scale))/(2*step))
    j=np.array(jac).T
    variance=np.maximum(np.einsum('ij,jk,ik->i',j,cov,j),0)
    if return_details:
        return t,variance,dict(theta=p,covariance=cov,jacobian=j)
    return t,variance


def correct_flux(flux,variance,transmission,transmission_variance,valid,*,minimum_transmission=.2):
    """Independent standard-model error plus science statistical variance.

    Return diagonal variances. Spectral covariance from the shared atmospheric
    parameters is retained separately, not claimed absent.
    """
    f,v,t,tv=np.broadcast_arrays(flux,variance,transmission,transmission_variance)
    good=np.asarray(valid,bool)&np.isfinite(f)&np.isfinite(v)&(v>=0)&np.isfinite(t)&(t>=minimum_transmission)&(t<=1.00001)&np.isfinite(tv)&(tv>=0)
    out=np.full(f.shape,np.nan);stat=out.copy();model=out.copy()
    out[good]=f[good]/t[good];stat[good]=v[good]/t[good]**2
    model[good]=f[good]**2*tv[good]/t[good]**4
    return out,stat+model,good,stat,model
