# Pipeline outputs

Browser-openable HTML reports from **EFOSpec** and **Spectypus**, hosted on GitHub Pages.
Published snapshot: **2026-11-18**. These are saved results; opening a page does not run either pipeline.

## Reduction logs and IRAF comparison

| Observing night | Report | Offline HTML |
| --- | --- | --- |
| 2024-11-14 | [IRAF comparison](https://doctorbrew.github.io/EFOSpec/2024-11-14/iraf-comparison.html) | [ZIP](https://doctorbrew.github.io/EFOSpec/2024-11-14/iraf-comparison-portable.zip) |
| 2024-11-14 | [Nightly reduction log](https://doctorbrew.github.io/EFOSpec/2024-11-14/index.html) | [ZIP](https://doctorbrew.github.io/EFOSpec/2024-11-14/index-portable.zip) |
| 2026-10-28 | [Nightly reduction log](https://doctorbrew.github.io/EFOSpec/2026-10-28/index.html) | [ZIP](https://doctorbrew.github.io/EFOSpec/2026-10-28/index-portable.zip) |
| 2026-10-29 | [Nightly reduction log](https://doctorbrew.github.io/EFOSpec/2026-10-29/index.html) | [ZIP](https://doctorbrew.github.io/EFOSpec/2026-10-29/index-portable.zip) |
| 2026-11-10 | [Nightly reduction log](https://doctorbrew.github.io/EFOSpec/2026-11-10/index.html) | [ZIP](https://doctorbrew.github.io/EFOSpec/2026-11-10/index-portable.zip) |

[All reduction reports](https://doctorbrew.github.io/EFOSpec/).
The November 10 log includes the full-spectrum wavelength checks and diagnostic
triplets for failed and unsupported exposures. Calibration warnings and partial
results remain visible; publication does not certify the reductions.

## Spectypus fitting and classification logs

| Dataset | Report | Scope |
| --- | --- | --- |
| ePESSTO+ observing night 2026-10-28 | [Classification and fitting log](https://doctorbrew.github.io/spectypus/nightly/2026-10-28/index.html) | Saved SNID/NGSF matches and reviewer log; belongs to the original classified reduction, not a refit of newer EFOSpec products. |
| Selected historical SLSN spectra | [Selected SLSN fitting log](https://doctorbrew.github.io/spectypus/reports/2026-11-10/index.html) | Report snapshot dated 2026-11-10; this is **not** the observing date of those spectra. |

[All fitting logs](https://doctorbrew.github.io/spectypus/).
Saved matches are classification candidates, not confirmed classifications.
Template banks and original source-file links are local dependencies; hosted
links explain that limitation. Saved plots and embedded evidence remain in the
reports. The full multi-object SpectralAtlas and development/QA pages are not
part of this published report set.

## Updating this index

- Both repositories keep this `OUTPUTS_PIPELINE.md` index. Use the HTTPS links
  above from GitHub; paths under `runs/`, `data/` and `results/` remain local and
  Git-ignored on the code branches.
- Pages serves report copies from each repository's **`gh-pages` branch, `/`**.
  New local pipeline runs do **not** automatically update the hosted snapshots.
- Replace only the chosen report copies and their referenced assets, verify
  local links/downloads, then commit and push `gh-pages`. Keep `.nojekyll`.
  Update the snapshot date and any new URLs in this index in both repositories.
- EFOSpec source entries are `runs/2024-11-14/`,
  `runs/2026-10-28/efosc/`, `runs/2026-10-29/` and
  `runs/2026-11-10/efosc/`. The two historical paths retain their existing layout.
- The nightly classification source is
  `EFOSpec/data/classifications/2026-10-28/index.html`. The selected SLSN report
  remains owned by the SLSN project under
  `Development/01_spectroscopicclassification/results/spectypus/reports/2026-11-10/`.
- Preserve source reports and numerical products. Publish copies; package
  large portable HTML files as ZIP downloads and do not substitute different
  spectra when a saved source-file link no longer resolves.
