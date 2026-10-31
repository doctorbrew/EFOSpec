# Manual extraction GUI

**Status: proposed next phase; no interactive GUI implemented yet.**

## Target workflow

1. Open a reduced exposure and inspect the native 2D image.
2. Accept automatic candidates or click to add an object.
3. Adjust trace anchors, width, and aperture; label objects **SN** and **galaxy**.
4. Paint sky inclusion/exclusion regions; preview the collapsed spatial profile.
5. Run extraction for the selected objects together.
6. Compare spectra, residuals, masks, and uncertainties; save a new revision.

## Recommended application shape

- Local browser application with the existing Fieldnotes styling.
- Python worker calls the same reduction/extraction functions as the CLI.
- Browser edits a saved recipe; it does not calculate scientific fluxes.
- Bind the service to localhost; no cloud upload required.
- Keep the automatic HTML report as the portable review/export product.
- A native macOS wrapper can come later if needed.

## What already exists

- PypeIt can accept multiple manual extraction positions.
- Installed 1.14.0 has `ManualExtractionObj`, `FindObjects`, and `Extract`.
- Our runner fits up to three detected candidates within a target-centred crop.
- It then selects and exports **only one** object.
- The current 141-pixel crop can exclude a distant galaxy or usable background.
- The current webpage displays results; it cannot change extraction settings.

## Backend work before the editor

- Separate image preparation, source selection, extraction, and export.
- Replace the single-target assumption with persistent object IDs.
- Feed manual positions/FWHM/radii into PypeIt's manual-extraction path.
- Keep requested objects and contaminating neighbours in the joint fit.
- Widen the crop when necessary; retain the complete crop-to-detector transform.
- Export both objects from one extraction pass, with separate masks and errors.
- Preserve the primary SN filename; agree a companion-product naming policy before implementation.
- Do not confuse an object index with the legacy exposure-number suffix.

## Saved recipe contract

| Item | Required meaning |
| --- | --- |
| Input | Raw-file hash, exposure ID, setup, calibration references |
| Coordinates | Zero-based native detector pixels; axis order `[spectral, spatial]` |
| Crop | Raw trim offsets and spatial crop origin |
| Objects | Stable ID, label, source type, anchor points, fitting policy |
| Aperture | Boxcar half-width in pixels; separate from fitted profile FWHM |
| Background | Inclusion/exclusion masks plus the fitting stage they affect |
| Extraction | Requested products and supported per-object methods |
| Revision | Parent recipe, engine version, settings, and output directory |

- PypeIt manual widths/radii are **pixels**; the default extraction radius is **arcseconds**.
- Convert display clicks through the saved geometry, never through guessed image scaling.
- A rectified wavelength display requires its actual wavelength map for coordinate conversion.
- V1 manual controls should set anchor positions, not claim arbitrary trace-curve control.
- Record whether the engine refits or holds a trace; test that requested control is honoured.
- Sky edits must affect extraction, not just the coloured overlay.
- Current mask recovery assumes automatic finding; manual recipes need capture during execution.
- Save new revisions; never overwrite an accepted spectrum.

## SN + galaxy: separate cases

- **Separated traces:** first supported two-source case.
- **Extended galaxy:** offer a boxcar spectrum first; validate any optimal profile model.
- **Overlapping SN/host:** two apertures alone do not produce a host-subtracted SN spectrum.
- **Deblending:** later work requiring an explicit spatial model and contamination tests.
- A shared sky fit can correlate the two spectra; do not imply their errors are independent.

## Delivery gates

| Step | Deliverable | Acceptance evidence |
| --- | --- | --- |
| G1 | Recipe + coordinate contract | Pixel/arcsecond conversions and crop round trips agree within 0.01 pixel |
| G2 | Headless manual / two-source extraction | Both IDs exported; distinct positions; primary naming preserved; old automatic recipe reproduces baseline |
| G3 | Trace/background editor | Save/reload preserves controls; CLI replay gives the same arrays; cancellation preserves accepted outputs |
| G4 | Extended/blended-source mode | Injected-source flux recovery, uncertainty coverage, and cross-contamination tested across separation and brightness ratio |

- G1 → G2 → G3; G4 requires its own scientific validation.
- For G2, test well-separated synthetic sources at ≥5 FWHM separation and several flux ratios.
- Initial synthetic target: median integrated-flux bias below 2% at SNR ≥30 across repeated noise realizations.
- Establish uncertainty-coverage and contamination limits before approving blended extraction.
- No-delta recipe regression: same arrays in the same engine/environment, within numerical precision.

## Naming proposal

- The current shortlist and rename strategy are tracked in [observer migration](adoption.md).
- The GUI should share the pipeline's selected name rather than introduce another product name.
- Describe it as “an experimental EFOSC2 reduction workbench”.
- Keep `epessto-plus`, `epessto_plus`, calibration paths, and product names until a rename is agreed.
- Names remain suggestions; the shortlist records limited registry checks, not a reservation.

## References

- [PypeIt manual extraction](https://pypeit.readthedocs.io/en/latest/manual.html).
- Local 1.14.0: `pypeit/manual_extract.py`, `find_objects.py`, `extraction.py`.
- Current wrapper: `src/epessto_plus/rapid.py`.
- Parent plan: [EFOSC2 migration](README.md).
