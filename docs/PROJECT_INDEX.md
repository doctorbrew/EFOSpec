# EFOSpec project index

This index routes readers to the existing owners of each topic.

| Folder | Contents |
| --- | --- |
| `guides/` | Current observing, desktop, review and delivery workflows |
| `science/` | Calibration, extraction policies and scientific limitations |
| `development/` | Contribution, testing and the retained browser prototype |
| `history/` | Dated investigations and validation evidence; not current instructions |
| `legacy/` | Original PESSTO/IRAF installation and compatibility |
| `manual/` | Authored standalone reduction manual and its assets |
| `references/` | External reference material |
| `roadmap/` | Local plans and design requirements |

Keep one guide per distinct workflow. Link to scientific policies rather than
copying them into each guide; retain dated evidence separately from instructions.

| Task | Start here |
| --- | --- |
| Install and reduce an observing date | [README](../README.md) |
| Find CLI options | [Command reference](../EFOSPEC.md) |
| Download, reduce, publish and locate nightly outputs | [Epoch workflow](guides/epoch-workflow.md) |
| Finish a spectrum, apply provisional flux and keep earlier spectra in the nightly HTML | [Reduction cookbook](guides/reduction-cookbook.md) |
| Package public/private spectra for WISeREP | [Delivery guide](guides/wiserep-delivery.md) |
| Edit source/aperture/background in the desktop app | [Desktop guide](guides/desktop.md) |
| Review host association and adopted redshift | [Typing metadata](guides/typing-metadata.md) |
| Understand calibration and extraction responsibilities | [Pipeline stages](science/pipeline-stages.md) |
| Understand raw masters and same-night flux responses | [Raw calibration](science/native-raw-run.md), [daily standards](science/daily-standard-calibration.md) |
| Understand background geometry and its limitations | [Bounded backgrounds](science/local-pypeit-background.md) |
| Understand acquisition markers, WCS and catalogue evidence | [Acquisition catalogues](science/acquisition-catalogues.md) |
| Assess what is scientifically validated | [Validation](history/validation-2026-10.md), [PypeIt 3 migration](history/pypeit3-migration-2026-11-10.md) |
| Work on the package and run checks | [Contributor guide](development/contributing.md), [CI](development/ci.md) |
| Understand tracked/local folders and compatibility shortcuts | [Repository layout](repository-layout.md) |
| Maintain legacy IRAF installation | [Legacy guide](legacy/legacy-installation.md) |

The active package lives in `src/efospec/`. `trunk/` is an independent preserved
legacy engine and a reference-data dependency, not a second active implementation.
Scientific limitations belong in their existing validation documents; this index does not redefine them.
