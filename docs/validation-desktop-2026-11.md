# Desktop and two-source checks — 2 November 2026

## Desktop acceptance

- Runtime: Python 3.11.18, PypeIt 1.14.0, PySide6 6.12.0; native macOS Cocoa.
- Real exposure: SN2023xxj, 2024-11-14, EFOSC2 Gr13, 2700 s.
- Edited the spatial anchor, aperture radius and saved background bands in Qt.
- Saved/reloaded the recipe; ran the extraction worker and opened its revision.
- Independent CLI replay matched flux, uncertainty and validity masks exactly.
- Parent raw inputs, calibration hashes and saved products remained unchanged.
- The 2026-10-28 dated folder opens both completed spectra and matching failed-exposure QC packets.
- Source review starts without a selected candidate; tests exercise extraction, cancellation and immutable products.
- Private images/products remain in gitignored dated validation folders.

Repeat on a local saved exposure:

```sh
python scripts/validate_desktop.py runs/2024-11-14 \
  --product tSN2023xxj_20241114_Gr13_Free_slit1.0_1_f.fits \
  --output runs/2024-11-14/validation/gui-check
```

## Conditional recovery

- Twelve synthetic scenarios: separation 0.5–2 SN FWHM, companion/SN flux 0.5 or 3, width ratio 1 or 3.
- Constant, linear and quadratic backgrounds; known Gaussian profiles and independent pixel noise.
- All conditional gates passed; largest absolute mean flux bias was **0.53%**.
- Identical profiles were rejected as degenerate.
- Six injections into the saved SN2023xxj background band, raw columns 306:344:
  - SN median bias: **−0.11% to +0.47%**.
  - Companion median bias: **+4.10% to +4.47%**.
- These six trials reuse one measured background; they do not calibrate independent background uncertainty.

## Failures retained in the report

| Synthetic mismatch | SN mean bias | Companion mean bias |
| --- | ---: | ---: |
| Companion width 20% too large | −0.08% | +15.19% |
| Companion centre offset by 1 pixel | +4.25% | −9.25% |
| Linear model for quadratic sky | −0.17% | −72.74% |
| Asymmetric companion fitted with one Gaussian | −5.05% | −6.47% |

- These fits retained valid rows despite biased fluxes and poor uncertainty coverage.
- A successful fit flag does not validate the spatial model or scientific separation.
- Formal errors exclude uncertain profiles, response calibration and inter-bin resampling covariance.

## Real companion sensitivity

- Chosen feature: raw spatial column **398**, near repeated summed-profile peaks and excess scatter.
- Assumed companion FWHM 5 pixels; background columns 310:332 and 415:440.
- Identity remains **unverified**; excess scatter can also arise from cosmic rays, fringing and sky residuals.
- Two spectra and their cross-source covariance were exported as a new revision; original products were unchanged.
- Changes below compare integrated counts over common valid bins, 4000–8500 Å, with the constant-background baseline.

| Perturbation | SN change | Companion change |
| --- | ---: | ---: |
| Linear background | −0.04% | −0.05% |
| Quadratic background | −8.99% | −85.82% |
| Companion width −20% | +0.05% | −19.81% |
| Companion width +20% | −0.21% | +16.73% |
| Companion centre −1 pixel | −0.13% | +6.92% |
| Companion centre +1 pixel | +0.17% | −5.76% |

- Held-out sky favoured constant/linear backgrounds; quadratic was outside the admissible set.
- These are sensitivity measurements, not accuracy estimates or errors to add in quadrature.
- General host-subtracted science remains unsupported; next validation needs a trusted target identification and spatial model/reference extraction.

## Reproduce

```sh
efospec validate-joint --output outputs/joint-check
# Add one explicit observed exposure; --recipe enables real-profile sensitivity:
efospec validate-joint --run runs/2024-11-14 \
  --product tSN2023xxj_20241114_Gr13_Free_slit1.0_1_f.fits \
  --recipe path/to/selected-joint-recipe.json \
  --output runs/2024-11-14/validation/joint-check
```

- Writes `validation.json`, a house-style PDF/300-dpi JPG and PNG preview.
- Reusing an output directory fails; input files are not modified.
- The real sensitivity recipe must explicitly select two sources; the validator does not identify a host.
- Local evidence: `runs/2024-11-14/validation/gui-20261102/` and `joint-observed-20261102/` in the development worktree.
- [Desktop guide](desktop.md) · [Launcher installation](desktop-installation.md) · [Existing engine validation](native-desktop-validation.md).
