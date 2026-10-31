# Browser extraction prototype

- **This is the existing experimental browser editor, not the requested desktop GUI.**
- Desktop application requirements and tasks: [roadmap](roadmap/pypeit-migration/gui.md).
- The separate Fieldnotes webpage remains a read-only log of each reduced night.
- The prototype is retained for backend testing and recipe experiments; desktop implementation is pending.

## Run the prototype

```sh
conda activate efospec
efospec gui runs/2024-11-14
```

- Opens a local browser tab; no uploads or additional runtime environment.
- Requires a completed rapid run, its original raw FITS, and matching archived references.
- `--reference-root DIR`: relocated reference library; content hashes must match.
- `--no-browser`: print the local launch URL; `--port NUMBER`: choose a port.
- Ctrl-C stops the service and cancels its active worker.

## Edit and extract

1. Select an exposure; inspect its spectrum, detector image, and wavelength-binned profile.
2. Choose **Manual anchors**; click a source or enter detector coordinates.
3. Set **FWHM** and **half-width** in pixels; optionally add a separated second source.
4. Choose background bands by dragging vertically, or enter their bounds.
5. **Save recipe** for replay; **Extract & save revision** runs PypeIt.
6. Inspect the fitted trace and residuals; switch between optimal and boxcar flux.

- Coordinates: zero-based raw detector pixels **after binning**; no extra factor of two.
- Anchors initialise PypeIt tracing; the fitted trace/profile can move.
- Red shading: requested boxcar aperture; dashed line: the displayed result’s fitted trace.
- Blue shading: sky input pixels, before iterative rejection.
- Controls show the current draft recipe; the revision selector chooses the displayed result.
- Selected sky bands span all spectral rows and exclude the requested source neighbourhoods.
- Keep at least 21% of the window for sky fitting; invalid recipes fail before extraction.
- Manual sky: fit the selected global background, then hold it during optimal extraction.
- Automatic sky: retain the existing global and local PypeIt fitting.

## Revisions and downloads

- Originals remain unchanged; every extraction gets a fresh `revisions/<ID>/result/` directory.
- Each revision saves `recipe.json`, source snapshots, input hashes, products, and report.
- Reload a recipe with **Load recipe**; completed revisions reappear after reopening the prototype.
- Download FITS, ASCII, recipe, or the offline report ZIP from the result controls.
- **Cancel extraction** terminates the worker; partial files remain in that revision for diagnosis.
- Primary filename: unchanged. Companion: `<primary-stem>_obj_<stable-ID>_f.fits`.
- Companion IDs do not replace the legacy exposure-number suffix.

Replay the same recipe without the browser:

```sh
efospec reextract runs/2024-11-14 \
  --product tSN2023xxj_20241114_Gr13_Free_slit1.0_1_f.fits \
  --recipe extraction-recipe.json --output runs/manual-replay
```

- Use a fresh output directory; `--skip-report` omits plot generation.
- Scientific products survive report-rendering failures; inspect the returned report status.
- Input hashes prevent replay against changed raw data, detector arrays, or calibration files.

## Current limits

- Saved detector window only; no crop widening or arbitrary trace-curve drawing.
- At most two requested sources, separated by ≥5 times their largest FWHM.
- Both sources are fitted together, including automatically detected neighbours.
- No overlapping-source deblending or host-subtracted SN claim.
- Extended galaxies: inspect boxcar extraction; their optimal profiles remain unvalidated.
- Shared sky fits can correlate errors; cross-source covariance is not stored.
- Prototype spectra retain the existing archived calibration; native raw calibration is still unfinished.

[Scientific validation](ci.md) · [Desktop GUI roadmap](roadmap/pypeit-migration/gui.md)
