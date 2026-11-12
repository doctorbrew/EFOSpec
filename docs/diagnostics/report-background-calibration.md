# Background and calibration report audit — 2026-11-12

The empty Background message was a presentation defect: `EpochPage.qc` searched for separate polynomial experiments and matching trial manifests but omitted the automatic background fits stored with current extraction products. The replacement section reads `processing.background_fit` and review-count `background` records. It retains failed-exposure counts and distinguishes fit convergence, masked rows and an unavailable geometry comparison. It does not rerun extraction or relax scientific checks.

The red calibration paragraph combined response construction, wavelength policy and absolute-flux limitations. The new summary reports saved response functions, delivered science products and recorded bias/flat/cosmic-ray processing first. Explicit unvalidated status remains visible. The saved limitations and failed response-transfer errors remain available in the same section. Fitting a response is not proof of absolute calibration.

## Saved-product verification

- **2026-10-28**, revision `20261110T170405Z-b97078`: verified hashes for 111 raw/calibration/response/diagnostic files covering all 10 delivered products. Six standard responses and six independent-exposure transfer calculations are recorded; none of those calculations raised an execution error.
- **2026-11-10**, revision `20261111T151006Z-e73ea3`: verified hashes for 91 files covering all six delivered products. Four standard responses and four independent-exposure transfer calculations are recorded; none raised an execution error.
- All checked detector archives contain nonzero fitted sky, accepted two-sided masks, at least five accepted samples per side on valid rows, and spatial degrees matching the manifest. Delivered FITS files contain native-calibrated flux and nonzero sky bands. The background minimum-side-sample counts agree with the saved arrays.
- Native master products and wavelength maps match their recorded hashes. The associated raw inputs and fitted response files also match. These checks demonstrate preserved products and recorded operations, not an independent astrophysical validation.

## Remaining scientific limitations

`geometry_unresolved` records inability to compare geometries with a clean withheld ring; the chosen default was still fitted. It does not mean no background was subtracted. Two rows are masked in the current AT2024afzf background fit, so the report must not claim every row is supported.

Short standard-star exposures use arc-only wavelengths by the reducer's explicit policy. The response fit masks stellar and telluric features and fits continuum zeropoints. This does not measure standard-star flexure or correct telluric absorption in the science spectra. Science sky validation is a separate gate; its failures remain failures.

The selected manifests explicitly mark independent absolute-flux validation as false. Narrow-slit losses, transparency variation, telluric absorption and second-order contamination are not fully corrected; response uncertainty and resampling/background-model covariance are not included in the formal spectrum errors. Independent photometry or suitable standards and a validated correction model are needed before claiming absolute-flux accuracy. A successful transfer calculation is not automatically a passed accuracy test.

## Git scope

The astrometry solver and previously accepted solutions were already in `origin/master` at `7780cc6`. This update publishes the pending host/astrometry-report consolidation and the evidence-based report corrections. In-progress extraction, calibration-route and sky-correlation changes in the working tree are outside this commit.
