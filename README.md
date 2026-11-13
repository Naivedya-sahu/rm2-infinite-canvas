# Infinite Canvas for reMarkable 2

Turns handwritten notebook pages on a reMarkable 2 into a canvas that grows **sideways** as well as downwards, inside the stock editor. You keep your native pens, layers, selection, eraser, undo/redo and file storage. A **house button** in the sidebar takes you back to the page's starting view.

Port of [bahadrdsr/remarkable-infinite-horizontal](https://github.com/bahadrdsr/remarkable-infinite-horizontal) (Paper Pure) to the reMarkable 2, as two small composable [QMLDiff](https://github.com/asivery/qmldiff) patches loaded by Xovi's Qt Resource Rebuilder.

> Unofficial. Not affiliated with or endorsed by reMarkable AS. This repository contains no reMarkable software or resources.

## Status — 0.1.2-r0

Tested by hand on a reMarkable 2 running OS 3.28.0.172:

| Feature | Status |
|---|---|
| Two-finger drag pans the canvas past the right page edge and down | ✅ works |
| One-finger swipe turns pages; swiping on the last page offers a new page (stock) | ✅ works |
| House icon in the expanded sidebar resets position and zoom; ink is untouched | ✅ works |
| PDFs and ebooks keep stock behaviour, including page swipe | ✅ works |
| Panning **left** of the original page edge | ❌ stops at the page edge (native limit, not addressed) |
| PDF export of ink drawn outside the original page | ⚠️ untested |

## Requirements

Strict, because the patches edit exact editor internals. The package refuses to install on anything else.

- reMarkable 2, OS **3.28.0.172** exactly (`/usr/bin/xochitl` SHA-256 `071d85beef3ef2d4cc0e11002140b27b82a2cc04a2ed740a5669f591069b77df`)
- [Xovi](https://github.com/asivery/xovi) with qt-resource-rebuilder 19.0.1-r0, installed via [Vellum](https://vellum.delivery)

## Install

1. Back up your notebooks (`/home/root/.local/share/remarkable/xochitl`).
2. Download `infinite-canvas-0.1.2-r0.apk` from the Releases page and copy it to the tablet.
3. Install the package. It is unsigned, so allow it for this one command only:
   ```sh
   /home/root/.vellum/bin/vellum add --allow-untrusted --no-network ./infinite-canvas-0.1.2-r0.apk
   ```
4. Save your work, then restart the editor. The package never restarts it for you. Either restart it yourself (`systemctl restart xochitl`), or copy `packaging/guarded-activation.sh` to the tablet and run it. The helper waits ~30 s, and if the editor fails to start cleanly it moves both patches aside and restarts the editor without them:
   ```sh
   sh guarded-activation.sh /home/root/infinite-canvas-activation
   cat /home/root/infinite-canvas-activation/result   # PASS or ROLLED_BACK
   ```

## Use

- **Two-finger drag**: pan and zoom the canvas.
- **One-finger swipe left/right**: change page; on the last page, swipe twice to add a page.
- **House icon** (sidebar expanded, notebook pages only): back to the default position and zoom.

## Remove

```sh
/home/root/.vellum/bin/vellum del infinite-canvas
systemctl restart xochitl
```

Removing the mod does not delete ink. Ink drawn outside the original page may not be visible in the stock editor afterwards, so export it first.

## How it works

| Patch | Edits | Effect |
|---|---|---|
| `src/infiniteCanvas.qmd` | `DeviceSceneView.qml` | `limitScrollingToPaper` is off for notebook pages; the dithered outside-paper overlays are hidden |
|  | `DocumentView.qml` | no horizontal snap-back to the page column |
| `src/infiniteCanvasHome.qmd` | `Toolbar.qml`, `DocumentView.qml` | native sidebar button (stock `house.svg`) that calls the editor's own `resetViewport()` |

A page counts as a canvas page only when `document.fileType === Document.Notebook && notePage`. Both patches start with `VERSION 3.28.0.172`, and every edit anchors on exact stock text, so a firmware change makes the patch fail instead of half-apply. There is no C++ helper, no service wrapper, no whole-file resource replacement and no binary patching. Other installed QMD mods keep working.

Unlike upstream, page swipes and the new-page button stay stock.

## Build from source

Needs your own tablet's files (not redistributable) and a QMLDiff build.

1. Copy `/usr/bin/xochitl` and `/home/root/xovi/exthome/qt-resource-rebuilder/hashtab` from your tablet to `.local/device/`.
2. Extract the editor's QML offline (it is parsed, never executed):
   `python tools/extract_resources.py .local/device/xochitl .local/resources`
3. Check the inputs are the reviewed versions: `python tools/preflight.py .local/resources`
4. Hash each QMD with your tablet's table: `qmldiff hash-diffs .local/device/hashtab <file.qmd>`
5. Stage the hashed QMDs into `home/root/xovi/exthome/qt-resource-rebuilder/`, and `LICENSE` into `home/root/.vellum/licenses/infinite-canvas/`. Then build the package on the tablet:
   ```sh
   apk.vellum mkpkg --files payload --info name:infinite-canvas --info version:0.1.2-r0 \
     --info arch:noarch --info license:MIT \
     --info depends:"rm2 remarkable-os=3.28.0.172-r0 qt-resource-rebuilder=19.0.1-r0" \
     --script pre-install:packaging/pre-install --script pre-upgrade:packaging/pre-install \
     --output infinite-canvas-0.1.2-r0.apk
   ```

`packaging/pre-install` only reads: it checks hardware, OS version and the editor's SHA-256, and changes nothing.

## Tests

```sh
uvx --with pyelftools --with capstone --with zstandard --from pyside6-essentials python -m unittest discover -s tests -v
```

- **Run anywhere:** the patch-source checks and the activation-guard checks.
- **Run only when you have your own extracted resources plus a local QMLDiff engine (otherwise skipped):** the integration tests. They apply the patches with the real QMLDiff engine, parse the output with Qt's `qmlformat`, run the patched JavaScript in `QJSEngine`, and check that bad firmware anchors and version mismatches are rejected and that the patches compose with other installed mods. The engine is expected at `.local/qmldiff-target-musl/debug/qmldiff`, run through WSL; adjust `engine()` in `tests/test_canvas_patch.py` for your setup.

Design notes: `SPEC.md` (original goals) and `PORTABILITY.md` (Paper Pure → rM2 analysis).

## Credits and license

MIT; see `LICENSE`. Canvas design by [bahadrdsr](https://github.com/bahadrdsr/remarkable-infinite-horizontal) (MIT). Patch language and engine by [asivery/qmldiff](https://github.com/asivery/qmldiff).
