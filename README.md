<img src="docs/brand/efospec-ntt-spectrum.png" alt="EFOSpec: stylized NTT enclosure above a spectral trace" width="580">

# EFOSpec — EFOSC2 spectroscopy with PypeIt

[![python](https://img.shields.io/badge/python-3.11-blue)](environment.yml)
[![build](https://github.com/doctorbrew/EFOSpec/actions/workflows/build.yml/badge.svg?branch=master)](https://github.com/doctorbrew/EFOSpec/actions/workflows/build.yml)
[![tests](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fdoctorbrew%2FEFOSpec%2Fbadges%2Ftests.json)](https://github.com/doctorbrew/EFOSpec/actions/workflows/build.yml)
[![coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fdoctorbrew%2FEFOSpec%2Fbadges%2Fcoverage.json)](https://github.com/doctorbrew/EFOSpec/actions/workflows/build.yml)

Reduce NTT/EFOSC2 spectra for ePESSTO with **PypeIt**, review extractions in the
PySide6 desktop app, and share a saved nightly report. Legacy IRAF/PyRAF workflows
remain available alongside the main Python pipeline.

## Three ways to reduce

| Route | Use it for | Commands |
| --- | --- | --- |
| **EFOSpec / PypeIt — primary workflow** | Raw calibration, extraction, desktop review and nightly reports | `efospec night`, `efospec gui` |
| IRAF/PyRAF — fast | A quick-look spectrum using archived calibrations | `PESSTOFASTSPEC` |
| IRAF/PyRAF — full | Bias/flat/arc processing, interactive extraction and standard-based calibration | `PESSTOEFOSC2dSPEC`, then `PESSTOEFOSC1dSPEC` |

**[Reduction Manual](manual_pessto.html)** — all three routes, step by step,
including frame lists, IRAF keyboard shortcuts and inspection plots.

IRAF routes use a separate PESSTO/PyRAF environment. The modernized legacy engine
lives on [pyraf-pipeline](https://github.com/doctorbrew/EFOSpec/tree/pyraf-pipeline);
keep its checkout beside EFOSpec. The PypeIt environment does not require IRAF.

## PypeIt quick start

```sh
git clone https://github.com/doctorbrew/EFOSpec.git
cd EFOSpec
conda env create -f environment.yml
conda activate efospec
```

Uses Python 3.11 and PypeIt 3.0.0. Scientific plots also require LaTeX, `dvipng`
and `type1cm`/`cm-super`. Retain the checkout for its calibration references.
[Installation details](EFOSPEC.md) · [Existing-user migration](docs/adoption.md).

Run one observing night at a time; replace the example date throughout:

```sh
efospec download 2024-11-14 --with-calibrations
python scripts/01_log_epoch.py 2024-11-14
python scripts/02_reduce_epoch.py 2024-11-14
python scripts/03_report_epoch.py 2024-11-14
efospec gui runs/2024-11-14/efosc
```

Skip downloading if inputs are already present. ESO access uses `ESO_USERNAME`
and `ESO_PASSWORD`, or `ESO_TOKEN`. Inspect the inventory before reducing.
Run the report after a partial reduction (exit 1); resolve input/operational errors
(exit 2). New reductions use same-night raw calibrations and standards.

Open `runs/2024-11-14/efosc/index.html`; share `index-portable.html` from the same
folder as a standalone report. GUI edits create new revisions; publishing them
to the nightly report requires the [reviewed-geometry workflow](docs/epoch-workflow.md#gui-revisions-and-nightly-publication).

## Files and outputs

| Location | Contents |
| --- | --- |
| `data/DATE/` | Original inputs |
| `runs/DATE/efosc/` | PypeIt reductions, calibrations, QA, logs and HTML |
| `runs/DATE/pessto/` | IRAF working copies, products, lists and logs |

Original inputs and previous revisions are preserved. Local observing data and
outputs are ignored by Git. Code lives in `src/efospec/`; `trunk/` retains the
legacy engine and reference calibrations.

## Status and documentation

**Experimental:** inspect source identity, extraction, wavelength and flux QA
before using spectra scientifically. Recent-night reductions can be partial;
real SN/host separation and absolute-flux accuracy remain unvalidated. Products
are not ESO Phase 3 certified. [Telluric correction](docs/telluric-correction.md)
is an explicit optional revision, not an automatic correction to every spectrum.

[Workflow and IRAF comparisons](docs/epoch-workflow.md) ·
[Desktop guide](docs/desktop.md) · [Calibration limits](docs/native-raw-run.md) ·
[Documentation index](docs/PROJECT_INDEX.md) ·
[Contributing](docs/contributing.md) · [Tests and CI](docs/ci.md).
