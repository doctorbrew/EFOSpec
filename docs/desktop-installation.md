# Desktop launchers

- Use the dedicated **`efospec` environment**, shared with CLI reductions.
- Requires the editable checkout, Python 3.11, PypeIt 1.14.0 and desktop/plot dependencies.
- Creates a small launcher; it does **not** bundle, download or replace the scientific runtime.

```sh
conda activate efospec
efospec install-desktop
```

| Platform | Default installation |
| --- | --- |
| macOS | `~/Applications/EFOSpec.app` |
| Linux | `$XDG_DATA_HOME/efospec/EFOSpec`, plus an Applications menu entry |

- Linux defaults `XDG_DATA_HOME` to `~/.local/share`.
- Launch from Finder or the Linux application menu; **Open night…** selects a dated folder.
- Existing installations are never overwritten. Remove the old launcher or choose `--destination PATH`.
- A custom destination stages the application there; it does not add a Linux menu entry.
- Keep the selected Python environment and checkout at their recorded paths.
- After moving/replacing either, reinstall the launcher from the desired environment.
- The macOS app is local and unsigned; this is not a notarized, self-contained download.

## Verification

```sh
efospec gui --smoke-test
# Test the installed macOS executable:
~/Applications/EFOSpec.app/Contents/MacOS/EFOSpec --smoke-test
# Or the default Linux launcher:
~/.local/share/efospec/EFOSpec/efospec-desktop --smoke-test
```

- Prints the Qt platform, loaded run and readiness, then closes the window.
- `runtime.json` records the interpreter, checkout, PypeIt and Qt versions.
- macOS Cocoa launch and GUI/CLI replay were checked locally.
- Linux CI validates the desktop entry and launches Qt/XCB under Xvfb; inspect the PR's actual result before claiming that revision passed.
- Launcher tests include spaces and shell metacharacters in installation paths.
- [Display dependencies and controls](desktop.md) · [Real-data validation](validation-desktop-2026-11.md).

## Remove a launcher

- macOS: remove `~/Applications/EFOSpec.app`.
- Linux: remove the `EFOSpec` launcher directory and `applications/org.efospec.Desktop.desktop` under the chosen data home.
- These launchers contain no observing data or scientific environment.

Bundle layout follows [Apple's bundle specification](https://developer.apple.com/documentation/bundleresources/placing-content-in-a-bundle); Linux entries follow the [Desktop Entry specification](https://specifications.freedesktop.org/desktop-entry/latest-single/).
