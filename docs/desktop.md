# Desktop extraction

- **Toolkit:** PySide6/Qt; real desktop windows, no web server.
- **Engine:** the active Python 3.11 / PypeIt 3.0 environment.
- **Nightly log:** separate, read-only webpage.
- **Validation:** macOS Cocoa interactions tested locally; Linux XCB/Xvfb interactions pass [CI](https://github.com/sPaMFouR/EFOSpec/actions/runs/41262157980).

```sh
conda activate efospec
python -m pip install -c constraints.txt -e '.[rapid,plots,desktop]'
efospec gui
# Or open a completed run directly:
efospec gui runs/2024-11-14/efospec
```

- Ubuntu/Debian display libraries, when absent:

```sh
sudo apt-get install libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0 \
  libxcb-icccm4 libxcb-keysyms1 libxcb-shape0
```

1. **Open night:** select a dated workflow folder or reduction containing `run.json`; later launches reopen it.
2. Select an exposure; inspect the spectrum, detector image and spatial profiles.
3. Use the source selector and labelled centre/FWHM/radius fields; click the 2D image to move an anchor.
4. Drag across the spatial profile to add background bands; edit exclusions if needed.
5. Save the recipe, then **Extract new revision**.
6. Expand **Revisions & activity**, open the completed revision, and inspect its diagnostics.

- Positions: zero-based raw detector pixels after binning.
- FWHM: spatial profile width; radius: boxcar half-width.
- Include/exclude bands: `lower:upper, lower:upper`.
- Source fields load measured values from the selected exposure.
- Automatic sky shows common bands from the saved mask in read-only boxes; its recipe still delegates the full mask to PypeIt.
- Turn automatic selection off to edit those bands; dragging a first band starts a fresh manual selection.
- Invalid controls disable extraction; **Inspect / Pan / Zoom** separate editing from navigation.
- Night preferences stay in local Qt settings; no user paths or observing data are shipped.
- Original raw files and accepted products remain unchanged.
- Cancellation stops extraction workers; partial revisions remain for diagnosis.
- Recipes bind to input hashes; CLI replay uses the same worker.
- Archived runs still require their archived references; native runs use their recorded raw calibration and response.

## Host and redshift review

The **Host & redshift** tab edits revision-bound host candidates and adopted
redshift metadata. Explicit acceptance is required; metadata saves never run
extraction or classification. See [metadata workflow](typing-metadata.md) for
review controls, the CLI, revision history and HTML refresh.

## Source review

- The second tab lists QC packets bound to the opened reduction.
- Open `review.json` directly for a failed exposure, including nights with no completed spectra.
- Select the trace explicitly; the application never chooses a target by brightness.
- Nightly-log **Open in EFOSpec GUI** links select that exact failed exposure. The recovery editor shows its raw filename; restart an already-open app after updating its code.
- **Extraction requirements**, above Extract, lists missing selections and recipe errors. Choose a candidate or use **Click aperture centre** on the plot, then enter or drag two background bands. Grey example text is not an entered band. Native recovery requires 15–50 pixels per side.
- Extract enables when the selected geometry is valid; the fit is checked before starting a worker. **Cancel extraction** is disabled until a worker starts. The editor distinguishes review counts from explicitly requested checked flux recovery.
- The plot toolbar exposes **Click trace**, **Drag background**, **Clear bands**, and **Save PDF + JPG**. Export uses 300-dpi JPG; Qt draws at native screen density. Deferred redraws retain the report's LaTeX/serif typography and 23.4-point tick labels. Spatial limits reuse the report's spike/edge exclusion rules, protect source apertures, and leave plotted samples and science arrays unchanged.
- Native review counts can **refit the trace with PypeIt** (degree 1–3) or explicitly **keep the saved trace for polynomial boxcar counts** (degree 0–3). The latter is an unvalidated experiment, not a repair of a rejected trace. Checked flux recovery retains wavelength/response gates; the GUI shows worker failure details and blocks known failed-parent three-line requests before launch.
- For saved-trace review counts: leave checked flux recovery off, choose **Review counts: keep saved trace (polynomial boxcar)**, select the candidate, drag one background band on each side, preview, then **Extract new revision** and choose a dated output parent. A successful fit does not clear a failed wavelength mask.
- Edit aperture/background bands, preview the polynomial fit, then save or extract a new revision.
- Choose a fresh output parent under that observing date.
- Current recovery output: count-level boxcar spectrum; no flux-calibration or host-subtraction claim.
- `background-gui review.json` remains an alias into this same application.
- [Polynomial background controls and limits](polynomial-background.md).

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

- Saved completed/failed detector windows only; no crop widening or arbitrary trace drawing.
- No automatic host identification or general extended-galaxy reconstruction.
- GUI plots support inspection; Fieldnotes exports retain the publication plot theme.
- Environment-backed macOS `.app` and Linux launchers: [installation](desktop-installation.md).
- Historical browser prototype: `efospec browser-prototype runs/2024-11-14/efospec`.

[Current acceptance results](validation-desktop-2026-11.md) · [Engine validation](native-desktop-validation.md) · [Desktop guide](desktop.md)
