"""Conditional spatial-profile extraction; not a generic SN/host deblender.

Rows must already share a wavelength across spatial pixels. Profiles are fixed
inputs, normalized over the supplied detector window. Covariance includes the
fitted polynomial sky and other source, but not uncertainty in those profiles,
the selected polynomial degree, or correlations from spectral resampling.
"""
import numpy as np
from numpy.polynomial.legendre import legvander


def _inputs(data, variance, sky):
    data, variance, sky = np.asarray(data, float), np.asarray(variance, float), np.asarray(sky, bool)
    if data.ndim != 2 or data.shape != variance.shape or sky.shape != data.shape:
        raise ValueError('data, variance, and background mask need matching 2D shapes')
    good = np.isfinite(data) & np.isfinite(variance) & (variance > 0)
    if min(data.shape) < 8 or np.any((good & sky).sum(axis=1) < 12):
        raise ValueError('background requires twelve finite positive-variance pixels per row')
    return data, variance, sky, good


def _degree(value):
    if type(value) is not int or not 0 <= value <= 2:
        raise ValueError('background degree must be 0, 1, or 2')


def choose_background_degree(data, variance, sky, max_degree=2):
    """Select the lowest order within one standard error of held-out sky error.

    Five contiguous spatial blocks are held out separately. Source pixels are
    never used. This is a model-choice diagnostic, not proof that sky is smooth.
    """
    _degree(max_degree)
    data, variance, sky, good = _inputs(data, variance, sky)
    x = np.linspace(-1., 1., data.shape[1])
    # Block assignments span the selected sky pixels, including both slit sides.
    folds = np.full(data.shape, -1, int)
    for row in range(len(data)):
        for fold, pixels in enumerate(np.array_split(np.flatnonzero(sky[row] & good[row]), 5)):
            folds[row, pixels] = fold
    scores = []
    for degree in range(max_degree+1):
        design = legvander(x, degree)
        fold_scores = []
        for fold in range(5):
            residuals = []
            for row in range(len(data)):
                train = (folds[row] >= 0) & (folds[row] != fold)
                test = folds[row] == fold
                weighted = design[train]/np.sqrt(variance[row, train, None])
                fit, _, rank, _ = np.linalg.lstsq(weighted,
                    data[row, train]/np.sqrt(variance[row, train]), rcond=None)
                if rank != degree+1 or not test.any():
                    raise ValueError('background support cannot constrain the requested polynomial')
                residuals.extend(((data[row, test]-design[test]@fit)**2/variance[row, test]).tolist())
            fold_scores.append(float(np.mean(residuals)))
        scores.append({'degree': degree, 'mean': float(np.mean(fold_scores)),
                       'standard_error': float(np.std(fold_scores, ddof=1)/np.sqrt(5))})
    best = min(scores, key=lambda item: item['mean'])
    admissible = [s['degree'] for s in scores if s['mean'] <= best['mean']+best['standard_error']]
    return {'degree': admissible[0], 'scores': scores, 'admissible_degrees': admissible,
            'background_model_uncertain': len(admissible)>1,
            'method': 'five_spatial_block_held_out_sky_one_standard_error'}


def extract_joint(data, variance, profiles, sky, *, background_degree=1,
                  clip_sigma=6., max_condition=1e4):
    """Fit up to two fixed profiles and a spatial sky polynomial simultaneously.

    Flux is total electrons per spectral row within the supplied profile window.
    Negative amplitudes are retained. Degenerate rows are invalid, never silently
    regularized into separate measurements. Formal covariance is conditional.
    """
    _degree(background_degree)
    data, variance, sky, good = _inputs(data, variance, sky)
    profiles = np.asarray(profiles, float)
    if (profiles.ndim != 3 or profiles.shape[1:] != data.shape
            or not 1 <= profiles.shape[0] <= 2 or not np.isfinite(profiles).all()
            or np.any(profiles < 0) or np.any(profiles.sum(axis=2) <= 0)):
        raise ValueError('profiles must be one or two finite nonnegative spatial distributions')
    if not np.isfinite([clip_sigma, max_condition]).all() or clip_sigma < 3 or max_condition <= 1:
        raise ValueError('invalid rejection or conditioning threshold')
    profiles = profiles/profiles.sum(axis=2)[:, :, None]
    count, rows, columns = profiles.shape
    polynomial = legvander(np.linspace(-1,1,columns), background_degree)
    ncoef = count+background_degree+1
    flux = np.full((rows,count),np.nan)
    covariance = np.full((rows,count,count),np.nan)
    coefficients = np.full((rows,ncoef),np.nan)
    full_covariance = np.full((rows,ncoef,ncoef),np.nan)
    operators = np.zeros((rows,ncoef,columns))
    background = np.full_like(data,np.nan)
    model = np.full_like(data,np.nan)
    valid = np.zeros(rows,bool)
    used = np.zeros_like(good)
    condition = np.full(rows,np.inf)
    chi2 = np.full(rows,np.nan)
    flags = np.full(rows,'insufficient_pixels',dtype='U30')
    for row in range(rows):
        design = np.column_stack([profiles[:,row,:].T,polynomial])
        support = np.any(profiles[:,row,:] > .001*profiles[:,row,:].max(axis=1)[:,None],axis=0)
        selected = good[row] & (sky[row] | support)
        original_count = int(selected.sum())
        for iteration in range(4):
            if selected.sum() <= ncoef+3 or (selected & sky[row]).sum() < 8:
                break
            weighted = design[selected]/np.sqrt(variance[row,selected,None])
            norms = np.linalg.norm(weighted,axis=0)
            if np.any(norms == 0):
                flags[row]='degenerate_profiles'
                break
            singular = np.linalg.svd(weighted/norms,compute_uv=False)
            condition[row] = singular[0]/singular[-1] if singular[-1]>0 else np.inf
            if condition[row]>max_condition:
                flags[row]='degenerate_profiles'
                break
            fit, _, rank, _ = np.linalg.lstsq(weighted,data[row,selected]/np.sqrt(variance[row,selected]),rcond=None)
            if rank != ncoef:
                flags[row]='degenerate_profiles'
                break
            residual = (data[row]-design@fit)/np.sqrt(variance[row])
            rejected = selected & (abs(residual)>clip_sigma)
            if original_count-(selected & ~rejected).sum() > .1*original_count:
                flags[row]='unmodelled_structure'
                break
            if rejected.any() and iteration<3:
                selected &= ~rejected
                continue
            if rejected.any():
                flags[row]='unmodelled_structure'
                break
            cov = np.linalg.inv(weighted.T@weighted)
            operator = cov@(design[selected].T/variance[row,selected])
            flux[row], covariance[row] = fit[:count], cov[:count,:count]
            coefficients[row], full_covariance[row] = fit,cov
            operators[row][:,selected] = operator
            background[row] = polynomial@fit[count:]
            model[row] = design@fit
            valid[row], used[row], flags[row] = True,selected,'ok'
            chi2[row] = float(np.sum(residual[selected]**2)/(selected.sum()-ncoef))
            break
    return dict(flux=flux,covariance=covariance,coefficients=coefficients,
                full_covariance=full_covariance,operator=operators,profiles=profiles,
                background=background,model=model,valid=valid,pixel_mask=used,
                condition=condition,reduced_chi2=chi2,flags=flags,
                background_degree=background_degree,
                uncertainty_scope='conditional_on_fixed_profiles_and_selected_background')
