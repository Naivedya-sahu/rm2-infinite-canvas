# Paper Pure -> rM2 portability assessment

## Verdict

Source-level UI portability is confirmed for the inspected rM2 OS 3.28.0.172 resources. Complete runtime compatibility is not yet demonstrated. The Paper Pure package must not be installed unchanged.

## New measured evidence

Compared SHA-256 of all six resources extracted offline from the owner's rM2 /usr/bin/xochitl with RESOURCES in upstream tools/build_native_patch.py. Every hash matched. Executed upstream transform(name, source) against each actual resource: every transformation passed without missing/ambiguous anchors. Nothing was installed or executed on tablet.

| Resource | Exact input hash | Transformation |
|---|---|---|
| DocumentView.qml | MATCH | PASS |
| DeviceSceneView.qml | MATCH | PASS |
| SceneViewGestures.qml | MATCH | PASS |
| Display.qml | MATCH | PASS |
| EditDocument.qml | MATCH | PASS |
| EditDocumentWindow.qml | MATCH | PASS |

These are structural/generator checks, not runtime QML instantiation, pen, persistence, export, or performance tests.

## Remaining port work

- Paper Pure device build is AArch64/Cortex-A55. rM2 is ARM32/armv7l. Rebuild settings/native helpers using matching rM2 SDK/Qt; do not bypass hardware checks.[4]
- Replace the Paper Pure-specific runtime service transition/boot wrapper with an independently reviewed integration into existing Vellum/Xovi loading. Its shutdown guard addresses behavior observed on Paper Pure, not behavior proved on rM2.[3]
- Package scoped files as Vellum APK; inspect hooks, avoid implicit restarts, and preserve rollback.
- Test coexistence with existing QML patches. In reviewed qt-resource-rebuilder/src/main.c, processNode() uses a replacement-first if/else: QRR replacement skips QMD processing for that resource. Prefer composable QMD hooks or explicitly compose and validate patches; do not assume QRR and QMD stack.
- Verify real extended ink, reopen/restart persistence, both notebook ages, and native tools. Existing/new notebook eligibility depends on notebook UUID/type, not creation date.[2]
- Native full-width PDF export remains unproven. Upstream edits editor/settings resources, not export bounds.[2]

## Paper Pure architecture

Host capture -> exact resource hash gate -> Python generator -> six modified owner-local QML files + .qrr replacement map -> Xovi + Qt Resource Rebuilder -> stock xochitl editor.[1][2][3]

A preloaded C++/Qt settings library registers CanvasSettings singleton in the editor. It stores global enablement and UUID-keyed per-notebook overrides in atomically written JSON. Invalid settings fail closed.[3]

Editor changes: relax limitScrollingToPaper for eligible handwritten pages; hide four outside-paper overlays; disable next/previous-page swipes; disable viewport snapping; hide edge new-page UI and guard page-change callbacks. Three further resources add global/per-notebook settings and Save integration.[2]

This reuses native scene rendering/input/storage rather than creating a second drawing engine. Two-finger pan/zoom is documented; page overview remains available.[1]

The runtime manager creates a runtime copy of xochitl.service with preload libraries, preserves service dependencies for sync, uses bounded startup verification/recovery, and optionally installs a one-shot boot activation unit. Do not transplant these device-specific lifecycle rules blindly.[3]

## Alternatives found

No second verified native horizontal-infinite rM2 implementation was found in this search. This is a search result, not proof no such project exists.

Related existing mods are not equivalents: createpages-paperpro makes finite new pages using Paper Pro dimensions; prevent-notebook-zoomout controls initial zoom/horizontal offset; disable-infinite-scroll restricts scrolling instead of extending it.[6]

Vellum search listings additionally show change-vertical-jump and scroll-screen-up-or-down as navigation helpers, not horizontal canvas extensions. Direct live catalogue fetch returned HTTP 403, so catalogue coverage relies on retrieved search listings.[5]

## Sources

[1] https://github.com/bahadrdsr/remarkable-infinite-horizontal
[2] https://github.com/bahadrdsr/remarkable-infinite-horizontal/blob/main/tools/build_native_patch.py
[3] https://github.com/bahadrdsr/remarkable-infinite-horizontal/blob/main/docs/ARCHITECTURE.md
[4] https://github.com/bahadrdsr/remarkable-infinite-horizontal/blob/main/CMakeLists.txt
[5] https://vellum.delivery
[6] https://github.com/rmitchellscott/xovi-qmd-extensions
