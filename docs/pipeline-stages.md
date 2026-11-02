# Reduction machinery

![Legacy IRAF and experimental native reduction](figures/reduction-machinery.svg)

| Stage | Legacy IRAF | Archive bridge (`reduce-rapid`) | Raw-only (`reduce-native`) |
| --- | --- | --- | --- |
| Inventory / names | `ntt` | EFOSpec / Astropy | Same association/naming contracts |
| Detector | `ccdproc` | Trim, gain, crop | PypeIt bias/flat, variance and masks |
| Wavelength | identify/reidentify, fitcoords | Fit archived IRAF pixel IDs | Physical He–Ar matching + PypeIt fit/tilts |
| Flexure | Legacy sky comparison | Two-line sky offset | Isolated 5577/6300; independent 6363 gate |
| Trace / sky | `apall` | PypeIt FindObjects/Extract | Same shared PypeIt engine |
| Extraction | Weighted / boxcar | PypeIt optimal / boxcar | PypeIt optimal / boxcar |
| Response | standard/sensfunc/calibrate | Archived response | PypeIt fit to observed standard + physical flux reference |
| Export | Multispec / ASCII | EFOSpec air-grid FITS/ASCII | Same filenames/bands; `FLUXCAL=NATIVE` |
| Review | Legacy interactive tasks | Qt desktop + Fieldnotes | Same desktop and read-only report |

- **IRAF runtime:** needed only for the preserved legacy pipeline.
- **Archived IRAF products:** used by the bridge; forbidden in the native path.
- **EFOSpec owns:** source identity, physical validation, naming, recipes, joint-profile solver and delivery.
- **PypeIt owns:** detector processing, slit/tilt/flat machinery, fitted wavelength model, ordinary extraction and native response fitting.
- **Joint mode:** EFOSpec's conditional weighted profile fit; it is not PypeIt's optimal extractor.
- **Scope:** EFOSC2 optical spectroscopy; no full legacy parity or Phase 3 certification.

## Errors and diagnostics

- Detector variance and flat scaling are preserved through native extraction.
- Delivered resampling propagates diagonal variance; wavelength-bin covariance is not stored.
- Joint mode saves source covariance and alternative backgrounds on its rectified count grid.
- Profile uncertainty, response uncertainty, slit losses and tellurics remain outside reported statistical errors.
- High spatial scatter can indicate source structure, sky residuals, fringing or defects.
- Blue shading: selected background. Red shading: geometric aperture, not optimal weights.

## Interfaces

- `efospec gui`: native PySide6 desktop; edit recipes, run/cancel and inspect revisions.
- `efospec browser-prototype`: retained experimental browser editor.
- `efospec report`: read-only Fieldnotes page; no extraction controls.
- [Desktop guide](desktop.md) · [Raw-only guide](native-raw-run.md) · [Validation](native-desktop-validation.md).
- Rebuild the SVG: `python scripts/render_pipeline_diagram.py`.
