# EFOSpec project index

This index routes readers to the existing owners of each topic.

| Task | Start here |
| --- | --- |
| Install and reduce an observing date | [README](../README.md) |
| Find CLI options | [Command reference](../EFOSPEC.md) |
| Download, reduce, publish and locate nightly outputs | [Epoch workflow](epoch-workflow.md) |
| Edit source/aperture/background in the desktop app | [Desktop guide](desktop.md) |
| Review host association and adopted redshift | [Typing metadata](typing-metadata.md) |
| Understand calibration and extraction responsibilities | [Pipeline stages](pipeline-stages.md) |
| Understand raw masters and same-night flux responses | [Raw calibration](native-raw-run.md), [daily standards](daily-standard-calibration.md) |
| Understand background geometry and its limitations | [Bounded backgrounds](local-pypeit-background.md) |
| Understand acquisition markers, WCS and catalogue evidence | [Acquisition catalogues](acquisition-catalogues.md) |
| Assess what is scientifically validated | [Validation](validation-2026-10.md), [PypeIt 3 migration](pypeit3-migration-2026-11-10.md) |
| Work on the package and run checks | [Contributor guide](contributing.md), [CI](ci.md) |
| Maintain legacy IRAF installation | [Legacy guide](legacy-installation.md) |
| Read cleanup and maintenance history | [Development log](DEVELOPMENT_LOG.md) |

The active package lives in `src/efospec/`. `trunk/` is an independent preserved
legacy engine and a reference-data dependency, not a second active implementation.
`AGENTS.md` contains repository rules for coding agents. Scientific limitations
belong in their existing validation documents; this index does not redefine them.
