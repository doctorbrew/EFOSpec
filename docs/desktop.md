# Desktop extraction

- **Toolkit:** PySide6/Qt; real desktop windows, no web server.
- **Engine:** the active Python 3.11 / PypeIt 1.14 environment.
- **Fieldnotes:** separate, read-only nightly report.
- **Validation:** macOS Cocoa and automated Qt interactions tested locally; Linux CI verification pending.

```sh
conda activate efospec
python -m pip install -c constraints.txt -e '.[rapid,plots,desktop]'
efospec gui
# Or open a completed run directly:
efospec gui runs/2024-11-14
```

1. **Open night:** select a directory containing `run.json`.
2. Select an exposure; inspect the spectrum, detector image and spatial profiles.
3. Click the 2D image to place the selected source; edit FWHM and aperture radius.
4. Drag across the spatial profile to add background bands; edit exclusions if needed.
5. Save the recipe, then **Extract new revision**.
6. Open the completed revision and inspect its trace, residuals and spectrum.

- Positions: zero-based raw detector pixels after binning.
- FWHM: spatial profile width; radius: boxcar half-width.
- Include/exclude bands: `lower:upper, lower:upper`.
- Automatic sky must have empty edited bands; invalid controls disable extraction.
- Original raw files and accepted products remain unchanged.
- Cancellation stops the worker process group; partial revisions remain for diagnosis.
- Recipes bind to input hashes; CLI replay uses the same worker.
- Archived runs still require their archived references; native runs use their recorded raw calibration and response.

## Extraction choices

| Choice | Behaviour | Limits |
| --- | --- | --- |
| PypeIt optimal + boxcar | Retrace manual anchors; fit profiles and sky | At most two requested sources, separated by ≥5 FWHM |
| Joint fixed profiles | Simultaneously fit one/two Gaussian profiles and polynomial background | Experimental; widths fixed, shared measured trace curvature |

- Joint background: constant, linear, quadratic, or selection from held-out sky.
- Automatic selection favours the simplest model within one standard error of the best score.
- Plausible alternative degrees are retained in `native/joint-covariance.npz`.
- Cross-source covariance is saved in **electrons² on the rectified grid**; fluxes are electrons/bin.
- Errors exclude profile uncertainty, response uncertainty and covariance between wavelength bins.
- Excess-scatter profiles help locate structure; cosmic rays, sky residuals and fringing can also produce peaks.
- A selected companion is a **candidate**, not a verified host galaxy.

## Limits

- Completed detector windows only; no crop widening or arbitrary trace drawing.
- No automatic host identification or general extended-galaxy reconstruction.
- GUI plots support inspection; Fieldnotes exports retain the publication plot theme.
- No packaged `.app`, installer or desktop shortcut yet.
- Historical browser prototype: `efospec browser-prototype runs/2024-11-14`.

[Scientific validation](native-desktop-validation.md) · [Roadmap](roadmap/pypeit-migration/gui.md)
