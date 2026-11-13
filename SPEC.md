# Native two-axis canvas — specification

## User decisions

C1. Extend native handwritten notebooks, not PDF/ebook annotation canvases.
C2. New notebooks and, if feasible, existing notebooks must extend horizontally after activation.
C3. Retain native vertical scrolling, pens, layers, selection, eraser, undo/redo, and storage.
C4. PDF export must include extended-page ink; do not assume stock export handles it.
C5. Read-only tablet inspection approved; install and editor restart require separate approval.

## Smallest shape

Owner tablet resources -> exact-version QML patch -> Xovi Qt Resource Rebuilder -> native xochitl editor.
Vellum APK/reManager installation; no separate drawing app or resident companion daemon.
Do not fake infinity with a fixed oversized page or alter existing notebook files offline.
Operationally unbounded, subject to native coordinates, memory and storage; not mathematical infinity.

## Gates

M1. Resolve exact native QML, native horizontal constraints and upstream prior art.
M2. Test-first patch generator; reject unexpected firmware/resource anchors. Produce offline-validated artifact.
M3. Package for Vellum without implicit restart, OS writes, or cloud changes. Preserve legal notices.
M4. Approved backup + install + restart; scratch notebook writing beyond both horizontal edges and downwards; native tool tests; close/reopen/restart persistence; existing notebook scratch-copy check.
M5. Export actual expanded scratch page to PDF; inspect bounds and visible ink. No release if cropped. PDFs/ebooks remain unchanged.

## Risks and open items

- Upstream bahadrdsr/remarkable-infinite-horizontal only supports Paper Pure, even on matching OS. Never bypass its installer device checks; design a separate rM2 patch based on measured resources.
- Native page bounds/export may be separate from viewport pan bounds.
- Horizontal page-change gestures must not steal canvas pans; page overview remains available.
- Assess active prevent-notebook-zoomout and gestik conflicts.
- Template coverage, thumbnails, cloud/mobile rendering and large-canvas performance need explicit validation.
- Default direction: retain native vertical growth semantics and add horizontal left/right extension; do not claim upward extension without proof.
