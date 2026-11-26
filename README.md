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

**[Open the Reduction Manual](https://doctorbrew.github.io/EFOSpec/manual_pessto.html)** —
all three routes, frame lists, IRAF keyboard shortcuts, inspection plots and
WISeREP packaging. [Offline HTML/source](manual_pessto.html).

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
efospec gui runs/2024-11-14/efospec
```

Skip downloading if inputs are already present. ESO access uses `ESO_USERNAME`
and `ESO_PASSWORD`, or `ESO_TOKEN`. Inspect the inventory before reducing.
Run the report after a partial reduction (exit 1); resolve input/operational errors
(exit 2). New reductions use same-night raw calibrations and standards.

Open `runs/2024-11-14/efospec/index.html`; share `index-portable.html` from the same
folder as a standalone report. GUI edits create new revisions; publishing them
to the nightly report requires the [reviewed-geometry workflow](docs/epoch-workflow.md#gui-revisions-and-nightly-publication).

## Restart a corrupt PypeIt reduction

From the EFOSpec directory with `conda activate efospec`, stop pipeline jobs and
close desktop reduction workers, then run:

```sh
# Show which PypeIt outputs would be moved, without changing any files.
python scripts/cleanup_epoch.py 2024-11-14
# Move all PypeIt outputs for this date into a recovery folder, preserving raw data and IRAF reductions.
python scripts/cleanup_epoch.py 2024-11-14 --apply
# Start a fresh reduction for this date using the original raw data.
python scripts/reduce_epoch.py 2024-11-14
```

The recovery copy is saved under
`runs/DATE/archive/cleanup-TIMESTAMP-ID/efospec/`; no products are deleted and
no disk space is reclaimed. Other observing dates are unchanged.
Equivalent command: `efospec cleanup-night DATE` (add `--apply` to move files).
See [lock handling and recovery instructions](docs/epoch-workflow.md#clean-restart-after-a-corrupt-reduction).

## Files and outputs

[Open published nightly logs, IRAF comparisons and Spectypus fitting logs](OUTPUTS_PIPELINE.md).

[Package reviewed spectra for WISeREP](docs/wiserep-delivery.md) using
`python scripts/package_wiserep.py`: separate public/private `.tgz` files with FITS,
ASCII, metadata and optional related files. Packaging does not upload data.

| Location | Contents |
| --- | --- |
| `data/DATE/` | Original inputs |
| `runs/DATE/efospec/` | PypeIt reductions, calibrations, QA, logs and HTML |
| `runs/DATE/pessto/` | IRAF working copies, products, lists and logs |

Original inputs and previous revisions are preserved. Local observing data and
outputs are ignored by Git. Code lives in `src/efospec/`; `trunk/` retains the
legacy engine and reference calibrations.

## Create the public and private upload tarballs

Open the [2026-11-10 observing log](https://doctorbrew.github.io/EFOSpec/2026-11-10/#delivery),
or a newly generated local `runs/YYYY-MM-DD/efospec/index.html`. **Science delivery**
is directly below the observing log:

1. Choose **Public**, **Private**, or **Do not export** for each target, and check
   **Object / Host**. The choice covers all eligible setups listed for that target.
2. Open **Observer / reducer names and delivery details**. Enter names, the UTC
   reduction date. Source and private groups are prefilled with **ePESSTO+**;
   private spectra also need an embargo end. Both group fields remain editable.
3. Confirm your review, click **Prepare public / private tarballs**, then download
   each populated archive. Observer/reducer names go into both the FITS headers
   and the upload table. Choices start unset and are cleared on reload.

This works offline, uses saved flux products and performs no upload. Standards,
count-only and failed products are excluded. Private delivery settings do not
make a publicly hosted observing log private. Use a local report for unpublished data.

For a saved review manifest and audit files, use the command line in the `efospec`
environment. Select the accepted PypeIt-derived `_f.fits`
products from one revision; replace the paths below with your selected files:

```sh
python scripts/package_wiserep.py init 2026-11-10 \
  runs/2026-11-10/efospec/nightly/REVISION/reduction/products/TARGET1_f.fits \
  runs/2026-11-10/efospec/nightly/REVISION/reduction/products/TARGET2_f.fits \
  --output runs/2026-11-10/efospec/delivery-review.json
```

Edit the JSON: set each spectrum's `visibility` to `public` or `private`, fill
observer/reducer attribution and review fields, and supply the private embargo
end time. Source group defaults to **ePESSTO+**; private entries without an override
inherit **ePESSTO+** from `private_defaults.associated_groups`. Public entries keep
`associated_groups: []`. Confirm the exact product hashes and review/release flags.
Then one command builds both tarballs and checks their contents:

```sh
python scripts/package_wiserep.py build \
  runs/2026-11-10/efospec/delivery-review.json \
  runs/2026-11-10/efospec/delivery/review-001

python scripts/package_wiserep.py validate \
  runs/2026-11-10/efospec/delivery/review-001/*.tgz
```

Share `pessto_YYYYMMDD_HH_MM_Rapid_upload_public.tgz` and
`pessto_YYYYMMDD_HH_MM_Rapid_upload_private.tgz` with the respective recipients.
The timestamp is the **UTC packaging time**, and `Rapid` is the reviewed quality.
Only populated access classes are produced; existing destinations are never
overwritten. Both classes must be present in the manifest to produce two tars.

The tarballs match the supplied `wiserep_tns_upload/` examples: a flat archive,
one `pessto_…_upload.txt` with the original header/defaults line, four-band
primary FITS and tab-separated two-column `.asci` spectra. Optional plots and
calibrated 2D products occupy the same related-file columns. Local masks, JSON,
error sidecars and checksums stay outside the upload tars. Native PypeIt `spec2d`
files are not relabelled as calibrated `_2df.fits`.
[Metadata fields and compatibility details](docs/wiserep-delivery.md).

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
