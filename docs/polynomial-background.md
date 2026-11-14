# Local background review and native editor

Delivered 2026-11-01: house-style QC for the four ambiguous October exposures, a native aperture/background editor, and an experimental covariance-aware polynomial boxcar engine. Both desktop editors now use PySide6. Full native-calibrated, flux-calibrated host subtraction remains unfinished.

## Inspect and edit

From the EFOSpec checkout and the existing `efospec` environment:

```sh
efospec background-gui 'runs/2026-10-28/QC/EFOSC.2026-10-29T05:12:40.988/review.json'
```

- Choose a candidate, or load `C3-background-degree2.json` from this QC folder.
- Click the aperture centre or type raw x/y; edit the boxcar half-width. Drag background bands or enter `520:535, 555:575`.
- Preview degree 0–3 and compare the data/fit and background-subtracted profile views. Degree 2 is the starting choice, not an automatically validated model.
- Save a new recipe, or extract to a new revision directory. Cancel terminates the subprocess; partial outputs may remain in that new directory. Raw data and parent products are unchanged.
- Qt is declared in the `desktop` optional dependency group; PypeIt 1.14 and the existing rapid/plot dependencies and LaTeX are also needed. This feature runs from the source checkout and uses its canonical `plot_style.py`.
- Native macOS evidence: `runs/background-gui-check/interactions-final/result.json`, logs and window screenshot. Actual canvas drags, saved-recipe replay, a successful extraction worker with arrays equal to the preview, cancellation and unchanged raw hash were checked. Offscreen tests are additional regression checks, not Linux desktop certification.
- This editor handles failed-exposure QC packets and one-source polynomial experiments. `efospec gui` opens the native completed-night browser and extraction controls; `efospec browser-prototype` retains the earlier browser editor.

## Native failed-exposure links (2026-11-13)

- Failed links and recovery entries in the Spectra exposure list open the native aperture/background editor in **Spectra**. Select a candidate, edit aperture and two finite 15–50 pixel background bands, preview, then Extract new revision.
- Same-night native failures no longer require archive calibration packets. The loader verifies the raw hash, calibration masters, exact processed detector crop and saved wavelength map before editing; recipes bind those inputs.
- Native previews use the processing inverse variance and bad-pixel mask. Wavelength failures remain masked in exported counts. The default remains experimental polynomial boxcar counts. The optional Checked native PypeIt + flux recovery control reruns native extraction with the explicit bands and a verified same-night response; it refuses wavelength-failed inputs and saves a separate revision. Neither route establishes validated host subtraction.
- macOS Cocoa interactions for all four failed science exposures, a real extraction, exact saved-recipe replay, cancellation and unchanged parent products are recorded in `runs/2026-10-28/nightly/20261113T141208Z-6fee4b/QC/gui-recovery/verification.json`. Linux native interaction verification has not been repeated for this change.

## Reproducible science contract

```sh
efospec background-extract runs/native-debug-20261101/recovery-run \
  --failed-raw EFOSC.2026-10-29T05:12:40.988.fits \
  --recipe runs/2026-10-28/QC/EFOSC.2026-10-29T05:12:40.988/C3-background-degree2.json \
  --output runs/2026-10-28/QC/C3-background-new-revision
```

The historical `native-debug-20261101/recovery-run` path is the retained failed-exposure evidence used by these recipes. Recipes bind the raw file, saved arrays and calibration manifest by SHA-256. Output directories must be new.

- Coordinates are zero-based raw detector pixels after binning. Bands are half-open `[lo,hi)`. At every detector row, any pixel touched by the fractional boxcar aperture is excluded from the background fit, even if it lies in a requested band.
- A saved candidate trace is shifted to the explicit integer-row anchor. The fit uses independent weighted Legendre polynomials per raw row, degree 0–3, with iterative rejection of the worst standardized residual and at least five valid pixels on each side.
- Use background sampling on both sides to infer the spatial slope: degree 1 fits a slope and degree 2 also permits curvature. Degree 0 is a constant comparison, not a slope measurement. Background bands should avoid source wings and neighbouring traces; the numerical side-count requirement alone does not establish uncontaminated sky.
- Invalid/saturated samples, insufficient one-sided coverage, ill conditioning, unconverged clipping, missing aperture pixels and incomplete aperture coverage produce masked rows. No extrapolated one-sided background is silently accepted.
- Data and read noise are electrons. Poisson plus read-noise variance feeds the fit. The extracted boxcar variance includes the **full polynomial coefficient covariance** integrated over the aperture, rather than a sum of independent model-pixel variances.
- Saved arrays include the model, coefficient covariance, actual fit mask, aperture weights, counts, variance and validity masks. FITS provides counts, sigma, interpolated background and air wavelength, with experimental/unverified metadata and `FLUXCAL=NONE`.
- This interpolates **local sky plus host**, not a separate physical host spectrum. Raw-row fitting does not account for wavelength-tilted narrow emission lines. Bias/flat calibration, aperture cosmic-ray rejection, trace uncertainty and model-choice systematics are not corrected here. It is not PypeIt optimal extraction.
- Multiple/unassociated trace failures now recommend aperture/background review and a two-sided polynomial preview. Host contamination is not automatically confirmed, and no target or subtraction is silently selected.

## Provisional C3 experiment

The user explicitly confirmed that C3 and these background bands apply to **SN2026aebl only** (the source identification remains provisional), exposure `EFOSC.2026-10-29T05:12:40.988.fits`. C3 is at raw x=548.843635559082, y=507; half-width=7 pixels. Background bands are `[520,535)` and `[555,575)`. Other exposures retain unverified candidate identities.

| Degree | Valid fit rows | Valid wavelength rows | Median extracted electrons | Median reduced chi² |
| --- | --- | --- | --- | --- |
| 1 | 1015/1015 | 942/1015 | 1966.25 | 0.948 |
| 2 | 1015/1015 | 942/1015 | 1471.52 | 0.805 |
| 3 | 1015/1015 | 942/1015 | 1375.27 | 0.709 |

These medians are per spectral row, not integrated/calibrated flux. Degree 2 is 25.2% below degree 1; degree 3 is 6.5% below degree 2. Lower chi² alone does not validate host removal. Fit-order sensitivity remains a material uncertainty beyond the formal errors.

See `runs/2026-10-28/QC/EFOSC.2026-10-29T05:12:40.988/C3-background-review.html`. The `C3-polynomial-degree{1,2,3}-v2` directories are the compared experiments; the initial degree-2 directory is retained as superseded processing history. All new/regenerated scientific figures use the house helper, LaTeX, Hiroshige, inward ticks, PDF and 300-dpi JPG, with PNG report previews. Plot configuration is scoped so it cannot leak into PypeIt's own diagnostic rendering.

## Method references

- [PypeIt sky subtraction](https://pypeit.readthedocs.io/en/stable/skysub.html): global/local sky models and extended-object limitations. Consult the installed 1.14 source for the pinned implementation; stable documentation may describe a later version.
- [IRAF aperture background](https://iraf.readthedocs.io/en/doc-autoupdate/tasks/noao/twodspec/apextract/apbackground.html): background bands and fitted local models.
- [IRAF row/column background](https://iraf.readthedocs.io/en/latest/tasks/noao/imred/generic/background.html): polynomial fitting and rejection along image rows/columns.

These references motivate local fitting; they do not validate this exposure's source identity or prove that a polynomial adequately describes its host.

Native-flux follow-up evidence: `runs/2026-10-28/nightly/20261113T141208Z-6fee4b/QC/recovery-followup-20261113/`. SN2026ayt passes bounded native extraction and wavelength checks. SN2026abgb's nearby-band trial completes but samples the broad neighbour's wing; it remains an unselected diagnostic trial. AT2026agvs/AT2026agzp remain wavelength-blocked. The report retains the original outcomes beside the checked manual recovery. Telluric extrapolation remains review-only.

## Nearby-band search (implemented)

`efospec background-search RUN --failed-raw RAW --recipe RECIPE --output NEW_DIR`
keeps one reviewed aperture/trace fixed and compares band displacements of −2,
0 and +2 pixels with spatial degrees 2 and 3. Each band remains 15–50 pixels;
aperture/core guards and explicit neighbour exclusions remain active. Common
withheld pixels rank PypeIt predictions independently of aperture flux and
training residuals. The selected model is refitted using all allowed samples.
This is local sky+host interpolation, not SN/host deblending. A lowest score is
conditional on the supplied geometry; close scores do not identify a unique
physical background. `search.json` retains every trial and the selected recipe.

Replay `selected-recipe.json` with `background-extract --native-counts` to export
new PypeIt review counts without requiring validated wavelengths. These retain
uncorrected arc wavelengths, masks and extraction uncertainties; background-model
covariance and model-choice uncertainty are not included. No old product is replaced.
The search is a CLI/backend feature; no new Qt control is claimed.

`efospec sky-compare RUN --failed-raw RAW --recipe RECIPE --output NEW_DIR`
compares sky sampled in the reviewed bands with PypeIt's Paranal sky template,
in vacuum wavelengths, across the full 5200–9000 Å interval and three separate
ranges. It retains shifts, correlation arrays, raw/calibration/source hashes and
template hash. This diagnoses flexure beyond the two-anchor check; it does not
yet replace wavelength acceptance or apply a correction to science products.
Full-spectrum matching follows PypeIt's `spec_flex_shift`; regional agreement
alone cannot establish reliability for featureless or contaminated spectra.

AT2026agvs (2026-10-28): all six background trials converged; common withheld-pixel
scores selected the original nearby bands and degree 2. Native review counts
were extracted. A temporary full-sky wavelength correction reduced regional
residual shifts to +0.65, −0.20 and +0.24 Å. Evidence is retained under the selected
nightly revision's `QC/agvs-background-search-20261114/` directory.
