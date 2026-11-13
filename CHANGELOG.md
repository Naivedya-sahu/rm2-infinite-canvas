# Changelog

## 0.1.2-r0 — 2026-11-13

First public release. Hands-on tested on a reMarkable 2, OS 3.28.0.172.

- Notebook pages extend past the right page edge and downwards with two-finger drag.
- Sidebar house button resets the page view (position and zoom); ink untouched.
- One-finger page swipe and the last-page new-page gesture stay stock. Earlier private builds disabled them, as upstream does.
- Guarded activation script with automatic rollback.

Known limits: panning left of the original page edge stops at the edge; PDF export of ink outside the original page is untested.
