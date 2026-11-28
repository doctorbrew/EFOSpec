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
- The plot toolbar exposes **Click trace**, **Drag background**, **Clear bands**, and **Save PDF + JPG**. Export uses 300-dpi JPG; Qt draws at native screen density. Deferred redraws retain LaTeX/serif typography and the user-requested compact tick labels. Spatial limits reuse the report's spike/edge exclusion rules, protect source apertures, and leave plotted samples and science arrays unchanged.
- Native review counts can **refit the trace with PypeIt** (degree 1–3) or explicitly **keep the saved trace for polynomial boxcar counts** (degree 0–3). The latter is an unvalidated experiment, not a repair of a rejected trace. Flux recovery reruns wavelength checks, retains failed checks in provisional outputs and requires a usable response; worker errors remain in Log.
- For saved-trace review counts: turn **Apply flux calibration** off, choose **Saved-trace boxcar counts**, select the candidate, drag one background band on each side, preview, then **Extract counts in new revision**. Output goes into a new dated manual revision automatically. A successful fit does not clear a failed wavelength mask.
- Edit aperture/background bands, preview the polynomial fit, then save or extract a new revision.
- Counts-only results remain uncalibrated. Native flux recovery may deliver a provisional flux spectrum with wavelength warnings; neither establishes host subtraction.
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

[Current acceptance results](../history/validation-desktop-2026-11.md) · [Engine validation](../history/native-desktop-validation.md) · [Desktop guide](desktop.md)


## Failed-exposure extraction workflow

- The header has one main tab row and one source/filename line. **Exposures** returns to the list; **Log** opens retained status, warnings and worker errors. Calibration stages and plot tools are in the sidebar so the detector panel can use the full window height.
- The recovery editor opens **2D aperture and extracted counts** by default. Preview shows the processed detector, saved trace, aperture and two background bands above provisional saved-trace boxcar counts. Detector-row coordinates remain explicit when wavelengths are unvalidated. This preview is not the PypeIt-refitted extraction result.
- **Wavelength calibration → Extraction → Flux calibration → Final spectrum** show short step statuses. Native recovery defaults to flux calibration. A persistent next-action button gently pulses three times when the next action changes. **Continue without trace cutoff** proceeds with trace warnings retained. Arc refitting is not implemented in these panels; failed sky checks are retained in explicitly provisional recovery products.
- Fresh extraction needs no recipe file or folder selection. The editor saves its recipe, worker logs and new output automatically under the selected reduction's `manual-revisions/`. Optional recipe import/export remains available.
- **Log** holds wavelength measurements, standard-star/calibration-file details and worker errors; these are hidden from the normal step panels. The wavelength-policy selector is under **Advanced wavelength checks**. Changing policy does not itself validate a spectrum. Same-night response availability does not establish absolute-flux accuracy.
- **Wavelength calibration** plots the saved arc lamp, identified lines, wavelength solution, fit/held-out residuals and separate science-sky checks. **Flux calibration** plots the selected standard's sensitivity zeropoints, physical sensitivity function and fit residuals, keeping excluded samples and unsupported gaps distinct. These read-only plots use the current saved spectrum's calibration associations and offer PDF + 300-dpi JPG export; missing or changed calibration files are reported instead of substituting another fit.
- A successful flux extraction automatically opens **Final spectrum**. Reopening the same exposure offers **View final spectrum** for the latest completed revision bound to the same raw input and parent. The plot reads the exported FITS, preserves masked gaps, labels provisional wavelengths and offers the output folder plus PDF/JPG export. Wavelength-check acceptance and flux-calibration application are reported separately.
- Verified on native macOS Cocoa; these new panels have not been verified on Linux.


## Trace and calibration warnings

- A fitted trace's departure from a degree ≤4 comparison polynomial is recorded, not rejected at 0.5 pixel. QA retains maximum/RMS departure, affected extraction-window rows and a warning. FITS keywords `TRCDEV`, `TRCWARN` and `TRCPOL=WARNING` carry the measurement and flag; extraction preserves the actual fitted trace.
- A failed parent wavelength check no longer disables a new calibrated-extraction attempt. The worker reruns wavelength validation and records the new outcome; a trace warning does not imply a failed wavelength solution or force one to pass.

- Manual native flux recovery retains a failed sky quality check as a warning and continues with the supported unshifted arc solution. The flux-calibrated output is explicitly **PROVISIONAL**, with `WAVEVAL=False` and the failed measurements preserved. It is not promoted to a wavelength-validated or accepted nightly product. Missing/invalid calibration inputs, unsupported geometry and absent flux response still produce errors.

- Recovery layout: tall vertical 2D detector at left, spatial profile at upper right, counts at lower right. Trace clicks and background drags work in either spatial panel and update both immediately. Candidate, centre, radius, anchor-row and band-field edits share the same overlays; clearing bands clears both panels. Changing geometry clears stale counts until **Preview** is run again. The profile shows the saved sky-subtracted row median; its aperture marker refers to the selected anchor row.

- Recovery GUI uses the requested compact typography: 17 pt axis labels, 16 pt panel titles, 14 pt legends and 18.2 pt ticks (14 pt base × 1.3). Smaller gaps enlarge the aligned plot panels; the GUI PDF/JPG export uses those same sizes.
