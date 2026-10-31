# Manual extraction GUI

**Status: first local workbench implemented.** [Run it](../../gui.md).

## Delivered

- One shared PypeIt extraction/export path for automatic and manual reduction.
- Validated, hash-bound recipes; zero-based detector coordinates and explicit pixel widths.
- Clickable trace anchors, numeric apertures, and draggable sky inclusion/exclusion bands.
- One or two separated sources; stable IDs and preserved primary filenames.
- Spectrum, detector image, wavelength-binned spatial profiles, and optimal/boxcar views.
- Saved revisions, recipe import/export, cancellation, and offline report downloads.
- CLI recipe replay; no browser-side scientific flux calculations.
- Localhost service; raw inputs remain local and unchanged.

## Evidence

| Gate | Acceptance evidence |
| --- | --- |
| Coordinates | Crop round trips and actual browser clicks/drags recover native pixels |
| Extraction | Three noise/brightness cases; separated synthetic sources recover median flux within 2% |
| Reproducibility | Automatic spectra unchanged; browser recipes reproduce headless arrays |
| Revisions | Original hashes preserved; cancellation and restart/history tested |
| Real exposure | SN2023xxj, 2024-11-14: manual sky/aperture extraction and report completed |

- Synthetic tests cover high-SNR point sources at ≥5 FWHM separation.
- Those tests do not establish blended-source or extended-galaxy accuracy.
- Manual anchors seed tracing; they do not constrain an arbitrary trace curve.
- Selected global sky remains fixed during optimal extraction; automatic mode retains local refitting.

## Next work

- Widen/rebuild the detector crop with explicit calibration geometry.
- Fit extended galaxy profiles; validate uncertainty coverage and cross-contamination.
- Develop an explicit overlapping SN/host model before claiming deblending.
- Preserve cross-source covariance from shared sky modelling.
- Add arbitrary trace constraints only with a tested PypeIt contract.
- Complete native raw calibration independently of this editor.

## Contracts

- Primary products retain the legacy exposure number and basename.
- Companion products append `_obj_<stable-ID>` before `_f.fits`.
- Recipes bind raw data, saved images, manifest, native spectrum, sensitivity, and extinction hashes.
- Every revision stores the executed Python source and engine versions.
- Background selections span spectral rows; source neighbourhoods remain excluded.
- All changes stay within a new revision; originals are never overwritten.

[Parent plan](README.md) · [Engine boundaries](../../pipeline-stages.md)
