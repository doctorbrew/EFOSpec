# EFOSpec calibration review — 28 October 2026

## Verdict

The previous blanket explanation was incomplete. Some limits reflect missing implementation, not missing observations. Other limits cannot be removed from the existing standard-star exposures alone. None should be cleared by changing status labels.

This review uses the retained `QC/nightly-integration-20261112/reduction` trial for **2026-10-28**, which includes all 12 extracted standards, including filtered Gr13 and red Gr16. It is not the selected nightly revision. No nightly pointer or accepted science spectrum was changed.

## Findings and changes

1. **High — standard-star wavelength checks were skipped outright.** Ten optical standards were tested with the unchanged 5577/6300 anchors and independent 6363 check. All ten fail using their narrow saved extraction windows. Reprocessing the full calibrated slit yields four passes: VMa2 Gr13/Free/slit1.0 and L745a Gr11/Free/slit1.0, Gr13/Free/slit1.0 and Gr13/Free/slit1.5. Measured corrections are approximately −5.6 to −7.1 air Å. The other six fail for weak/constrained lines or inconsistent anchors. Gr16 cannot use this optical three-line gate.

   **Fixed:** the native optical reducer now attempts the same full-slit check on standards and science. Passing standards get their own measured shift. Failed standards retain their unshifted arc grid, the actual measurements and failure reason; science failures remain fatal to validated wavelength delivery. Unexpected exceptions are not swallowed. `sky-check.json` persists the outcome. Sky validation still does not establish a point source's across-slit centring or stellar radial velocity.

   **Real extraction check:** VMa2 Gr13/Free/slit1.0 was freshly extracted and its response rebuilt in the separate audit directory. The applied shift is −6.7479 Å and the independent check passes. Existing products were preserved. This demonstrates the standard path works; it does not certify that every science spectrum calibrated with it improves.

2. **High — telluric correction was absent in the audited reduction.** Response fitting masks atmospheric bands, but applying a smooth sensitivity function does not remove atmospheric absorption from science spectra. The ten standards with O2 A coverage show median band/adjacent-continuum ratios of roughly 0.67–0.73. These are measured depressions, not fitted atmospheric transmission or a validated correction. Gr11 does not cover this band. The review code measures O2 B, H2O and O2 A separately and reports missing coverage explicitly.

   **Subsequently implemented:** [PypeIt atmospheric PCA fits and independent transfer validation](../telluric-correction.md), with native-sample integration, fitted resolution/offset, covariance, per-band rejection and separate review exports. In `QC/telluric-20261112-v3`, all 12 testable directed O2 A transfers pass (RMS 21–25% before, 3.2–5.6% after); all 14 H2O 7200 tests pass. Five O2 B tests fail, and 8200-Angstrom coverage after masks is insufficient. Both science review products exceed the tested airmass difference and remain explicitly unvalidated extrapolations. The selected nightly reduction remains unchanged. The six-hour standard separation does not establish atmospheric stability for every intervening exposure.

3. **High — Gr13 second-order handling is missing.** The retained data do contain suitable same-star, same-slit Free/GG495 pairs. A new isolated trial implementation splices their zeropoints near 5500 Å, with additive magnitude normalization, a documented grey-throughput assumption, no gap bridging and no red extrapolation. It never enters nightly response selection.

   Three available pairs were tested against another star's Free exposure with the same setup. One trial worsens the maximum continuum colour residual from 6.2% to 7.3%; the other two reduce it from 7.7% to 6.2% and from 7.1% to 6.1%. These are band-summary diagnostics after removing a grey scale, not total error estimates or a pass threshold. They use the original arc-only counts; wavelength alignment, filter throughput and different flat-field responses remain confounded. The trial is **not adopted**. Both stars are relatively cool white dwarfs: this does not validate a correction for a very blue science target. A corrected standard sensitivity also does not subtract additive second-order photons from science data. Gr16 already has the physical OG530 order-blocking filter; a blanket warning about missing software correction must not imply every setup has identical contamination.

4. **Medium — flux QA mixed continuum, stellar features and atmospheric absorption.** A global median could look close to unity while hiding colour-dependent residuals. **Fixed:** standard-recovery QA now masks hydrogen, helium and telluric regions for continuum bands and reports equal-weight band scale and residual colour separately. Old all-sample medians remain explicitly identified for compatibility. Same-exposure closure never becomes independent validation. Distinct exposures of the same reference star are distinguished from different-star transfers. Missing bands remain missing; >8200 Å coverage is not certified by the selected continuum summaries.

5. **High for absolute spectrophotometry — slit loss and absolute scale remain underdetermined.** Cross-standard repeatability does not separate transparency, centring, seeing, aperture losses, reference-system differences and throughput. The along-slit spatial profile does not measure photons lost across the slit. No contemporaneous calibrated target photometry or across-slit centring measurements are supplied to this audit. Applying a universal Gaussian correction from along-slit FWHM would introduce an unvalidated model.

   **Required evidence:** calibrated, contemporaneous target photometry with passbands and uncertainties, or suitable wide-slit observations and measured centring/seeing. Compare synthetic and observed photometry on their common supported wavelength range before fitting a scale/colour correction; retain independent bands/epochs for validation. Extended host emission and the point source need separate aperture treatment. Calibration uncertainty must remain distinct from statistical extraction errors.

## Evidence and reproduction

- Audit: `runs/2026-10-28/QC/calibration-audit-20261112-v2/audit.json`; source snapshot, physical-reference checksums, 14 standard transfers, three paired-response trials, and before/after hashes of 255 protected files.
- Initial full-slit audit and fresh VMa2 extraction: `QC/calibration-audit-20261112-v1/standard-refit-vma2-gr13/result.json`.
- Response trials affect only files inside their new audit directories. They are not approved science responses, and no telluric/slit-loss correction was applied to accepted spectra.
- Verification: 32 focused tests passed, including synthetic raw photons through real PypeIt calibration, extraction and flux export. After adding persisted standard-check assertions and the telluric-depression regression, the four affected tests also passed. The initial new standard-policy and flux-validation tests failed before implementation and passed afterward. The full repository suite was not rerun.

```sh
python -m efospec.calibration_audit 2026-10-28 \
  --run runs/2026-10-28/QC/nightly-integration-20261112/reduction/run.json \
  --output runs/2026-10-28/QC/calibration-audit-NEW --measure-sky
python scripts/plot_calibration_audit.py runs/2026-10-28/QC/calibration-audit-NEW/audit.json
```

## Scientific references

- [PESSTO survey and reduction description, sections 3.2–3.4](https://arxiv.org/html/1411.0299v2): standard wavelength checks, paired-filter sensitivity construction, atmospheric model correction, and photometric validation. This motivates the experiments; it does not certify these new implementations.
- [ESO EFOSC2 order sorting](https://www.eso.org/sci/facilities/lasilla/instruments/efosc/inst/order-sorting.html): configuration-dependent second-order contamination and filter throughput.
- [PypeIt flux calibration](https://pypeit.readthedocs.io/en/stable/fluxing.html): sensitivity fitting does not remove differential slit losses.
