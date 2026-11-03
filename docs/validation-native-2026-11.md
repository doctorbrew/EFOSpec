# Native acceptance — 3 November 2026

## Delivered

- PR #3 merged; default-branch CI published **231 passed / 91.8% coverage**.
- macOS app installed at `~/Applications/EFOSpec.app`, using the dedicated `efospec` environment.
- Installed-environment SN2023xxj GUI extraction matched CLI replay exactly; inputs remained unchanged.
- Fresh Gr13/Free raw reductions completed for one exposure on each October night.
- Python file-open/import guards recorded **zero** legacy calibration or IRAF/PyRAF access attempts.
- Raw-file hashes, air-wavelength delivery, original filenames and four flux bands were preserved.

## Measured results

| Diagnostic | 2026-10-28 | 2026-10-29 |
| --- | ---: | ---: |
| Arc RMS, standard/science (pixel) | 0.073 / 0.073 | 0.068 / 0.071 |
| Held-out arc RMS, standard/science (pixel) | 0.099 / 0.099 | 0.088 / 0.097 |
| Held-out 6363 Å sky residual (Å) | −0.17 | −1.94 |
| Valid delivered flux bins | 24.9% | 24.9% |
| Robust sky-residual scatter / model sigma | 1.02 | 1.11 |

- Both wavelength checks pass existing gates; **broad flux support fails**.
- The response supports only roughly 5650–6960 Å. Unsupported samples remain masked.
- Noise statistics use fitted sky/model residuals; they do not establish independent uncertainty coverage.
- One exposure per night is an experiment, not validation of every setup or the whole night.

## Independent standard check

- October 28 response: L745-46A through slit1.0; a separate slit1.5 exposure was excluded from fitting.
- Training-standard median recovered/reference flux: **0.998**.
- Held-out exposure median recovered/reference flux: **1.418**.
- Different slit widths, seeing and transparency can affect this comparison; their contributions are not isolated.
- No renormalisation or relaxed calibration thresholds were applied.
- Do not interpret training agreement as independent absolute-flux accuracy.

## Repairs and gates

- Reproduced a paired-run acceptance gap: plausible central wavelength/dispersion allowed incorrect detector endpoints.
- Both native identification routes now share endpoint, spectral-coverage and held-out residual acceptance gates.
- Cached paired-run masters must pass current wavelength checks as well as hashes.
- A deliberately shifted, rehashed cache is rejected; altered master bytes are rejected separately.
- New runner reports coverage by 500 Å interval, standard recovery, residual noise and explicit failed diagnostics.
- Diagnostic coverage target: ≥80% valid samples per interval over 4000–8500 Å; **not** a scientific-certification threshold.
- [Commands and exit codes](native-raw-run.md#validate-a-delivery).

## SN + companion check

- Repeated SN2023xxj validation: all twelve matched-profile synthetic cases pass.
- Real companion counts still change about **−20%/+17%** for a ±20% width change.
- Quadratic background remains outside the held-out sky selection's admissible set.
- No trusted host identity/reference extraction is available; general host subtraction remains unvalidated.
- [Detailed tests and limits](validation-desktop-2026-11.md).

## Next scientific work

- Investigate response-fit support with wavelength-block holdouts; do not promote smoothing choices solely for wider coverage.
- Validate same-slit or wide-slit standard transfer and wavelength-dependent throughput.
- Register acquisition positions and establish reference extractions for difficult targets.
- Retain the default nightly calibration mode until native delivery passes these checks.

## Local evidence

- Development worktree: `EFOSpec-worktrees/native-desktop`.
- Raw-only runs: `runs/2026-10-28/validation/native-delivery-20261103-recorded/` and `runs/2026-10-29/validation/native-delivery-20261103/`.
- Joint checks: `runs/2024-11-14/validation/joint-acceptance-20261103/`.
- Installed desktop: main checkout's `runs/2024-11-14/validation/installed-desktop-20261103/`.
- Proprietary identifiers, FITS, detailed logs and plots remain Git-ignored.
