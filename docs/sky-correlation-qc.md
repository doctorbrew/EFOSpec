# Full-spectrum wavelength failure diagnostics

Delivered: native `full-spectrum` failures automatically retain a
`sky-diagnostics/packet.json` and hash-bound `arrays.npz` alongside
`sky-check-failed.json`. Diagnostic I/O failures are recorded without hiding
the original wavelength rejection. No installed PypeIt files are modified.

The packet includes the calibrated detector window, original air wavelength
map, exact sampling mask, sampled sky, resolution-matched observed/template
spectra and PypeIt's seven correlation samples and fitted coefficients. Both
measurement stages are retained if failure occurred after correction.

## Inspect a failure

Use the EFOSpec environment and a fresh directory inside that night's QC revision:

```sh
python -m efospec sky-diagnose \
  runs/2026-10-28/efosc/nightly/REV/reduction/wavelength-review/exposures/RAW/sky-diagnostics/packet.json \
  --output runs/2026-10-28/efosc/nightly/REV/QC/sky-diagnosis-NEW \
  --trial-correction
```

`python -m efospec.sky_diagnostics` provides the same interface. Earlier failures
lack the newly captured arrays: replay their original hash-verified native
window and exact sampling mask into a new diagnostic revision. Do not transfer
curves from a different extraction or guess the mask from display shading.

The command writes structured measurements, arrays, execution logs, source
snapshots and PDF + 300-dpi JPG plots using the root `plot_style.py`.
It creates no standalone diagnostic HTML. Retain review notes in the main
nightly report; show the plots directly when discussing a failure.

- Sky/template overlays use high-pass filtering and L2 normalization for display;
  twenty edge samples are omitted to match the normalized-correlation check.
- Peak plots retain PypeIt's original samples and quadratic, plus the separately
  normalized high-pass correlation. This diagnostic uses a quarter-pixel grid.
- Controlled trials vary the quadratic window (3/5/7 samples), trim 2/5/10/20
  samples from each edge, remove only the initial observed-sky percentile clip,
  or remove only the later line-amplitude ceilings.
- Clipping trials implement PypeIt **3.0.0** processing. They must reproduce the
  saved baseline correlation and peak before reporting alternatives. Other
  versions and mismatches explicitly suppress those trials; original plots remain.
- Optional correction trials remeasure the full-range offset on a temporary
  wavelength map only when the full-range quality checks pass. They never modify
  the saved spectrum, apply a correction, or activate a report selection.

## Interpretation and limits

The summary names weak/ambiguous peaks, coverage, fit-shape, estimator mismatch,
regional spread and corrected-residual failures. A single discrepant region
with a sound full-range measurement and two consistent remaining regions is
labelled a **localized warning candidate**. This is a review aid, not automatic
wavelength acceptance. Existing `full-sky-v1`, background and telluric gates remain
unchanged; diagnostic alternatives do not certify a better wavelength solution.

SN2026abgb motivated this workflow. Its saved shifts reproduce exactly. The red
estimate changes from -0.061 to -0.613 pixel when the initial observed-sky clip
alone is disabled; changing peak width or trimming edges does not resolve it.
The same change affects other regions, so it is not a global clipping fix.
The delivered provisional flux spectrum remains unchanged.
