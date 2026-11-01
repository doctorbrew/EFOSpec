# Native/desktop validation — 2026-11-01

- Branch: `feature/native-desktop`; isolated from the active two-night debugging checkout.
- Proprietary inputs, products and detailed logs remain gitignored.

| Check | Evidence | Boundary |
| --- | --- | --- |
| Raw Gr13 arc | 16 retained lines; 0.39 Å fit RMS; 0.34 Å whole-line holdout RMS | One real configuration; no archived pixel IDs |
| Independent science sky | 6363 Å residual −1.94 Å after two-line correction | Acceptance limit 3 Å; not precision velocity calibration |
| Raw-to-product run | Bias/flat/arc + observed L745 response → FITS/ASCII + Fieldnotes | Only ≈5655–6958 Å supported by this response; ≈25% valid output bins |
| Synthetic raw photons | Actual PypeIt masters, extraction, flux export and exact replay | Tests block reads from legacy reference paths |
| Synthetic overlapping profiles | Recovery, conditional covariance, degeneracy and mismatched-profile rejection | Known Gaussian profiles |
| Injections into observed background | Six trials; median flux errors <0.5% for both sources | Same background realization; no real host truth |
| SN2023xxj trial | Two candidate components exported; constant/linear backgrounds admissible | No trusted host reference; no host-subtracted science claim |
| Background sensitivity | SN median 1626.8 vs 1629.5 electrons/bin: ≈0.2% | Tests only the selected profile geometry |
| Qt desktop | File picker, source edits, sky bands, recipe reload, worker, cancel/restart, revision open | macOS Cocoa locally; Linux XCB/Xvfb in CI |
| Linux build/tests | 170 passed; 91.7% package coverage; wheel and dependency check passed | Tested source `bbd82c0`; no proprietary fixtures |

- Verified [CI step logs and metric artifacts](https://github.com/sPaMFouR/EFOSpec/actions/runs/41262157980).
- Feature-branch metrics do not overwrite the README's `master` badges.

## Critical findings

- An unconstrained arc search gave a small RMS but a negative central wavelength; physical checks reject it.
- A wide 6363 Å fitting window can pick the stronger 6300 Å wing; isolated fits have regression tests.
- Large spatial scatter also occurs away from the SN: it cannot identify a host by itself.
- The SN2023xxj sky supports constant/linear models; quadratic is disfavoured by held-out sky.
- Fixed-profile uncertainties do not include uncertain morphology or wavelength-bin correlations.
- The archive bridge and raw-only path remain explicitly separate.
- The real standard's spline loses support near both spectral ends; science counts remain valid.
- Finer response knots increase support in exploratory fits, but need independent validation before adoption.
- Source identity, absolute flux and full-range native flux calibration remain unverified.

[Desktop usage](desktop.md) · [Raw-only usage](native-raw-run.md)
