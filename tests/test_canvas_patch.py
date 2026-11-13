"""Behavioural integration tests for src/infiniteCanvas.qmd.

Every test drives the REAL QMLDiff engine (local musl build of upstream core,
run through WSL) against the owner's extracted rM2 3.28.0.172 resources.
Emitted QML is then checked with Qt's own parser (qmlformat) and the patched
bindings/functions are executed with Qt's QJSEngine.

Run (from project root):
    uvx --from pyside6-essentials python -m unittest tests.test_canvas_patch -v

Owner-local fixtures (.local/resources, .local/device/hashtab) are read only,
never copied into distributable paths. Engine output goes to
.local/canvas-test-output/ (overwritten each run) and temporary directories
under .local/canvas-test-tmp/.
"""

import difflib
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

QMD = ROOT / 'src' / 'infiniteCanvas.qmd'
FIXTURES = ROOT / '.local' / 'resources'
HASHTAB = ROOT / '.local' / 'device' / 'hashtab'
LOCAL = ROOT / '.local'
OUTPUT = LOCAL / 'canvas-test-output'
TMP_PARENT = LOCAL / 'canvas-test-tmp'
FIRMWARE = '3.28.0.172'

DOCVIEW = 'qml/device/view/documentview/'
DSV = DOCVIEW + 'DeviceSceneView.qml'
SVG = DOCVIEW + 'SceneViewGestures.qml'
DV = DOCVIEW + 'DocumentView.qml'
# Exact reviewed inputs (same digests as upstream tools/build_native_patch.py).
PINNED = {
    DV: '867b30a725a4ae97e3459f07a60cd72bcafb21db9a0b374f02d75c5cd8d83269',
    DSV: '78df7fe68f0be6e0795cde67bdb5ce5c5f355c9100f0c14d6e8157c688271a0c',
    SVG: 'ab11773343d512d7f1e4259411c91ed2aff5c222c787cccd2e8d076b4e33563f',
}
# Resources the canvas patch rewrites. SceneViewGestures stays stock so
# one-finger page swipe / swipe-to-add-page keep native behaviour.
PATCHED = (DSV, DV)


# --------------------------------------------------------------------------
# Real-engine harness
# --------------------------------------------------------------------------

def wsl_path(path):
    path = Path(path).resolve()
    drive = path.drive.rstrip(':').lower()
    return '/mnt/' + drive + path.as_posix()[len(path.drive):]


def engine(*args):
    musl = wsl_path(LOCAL / 'alpine/lib/ld-musl-x86_64.so.1')
    libs = wsl_path(LOCAL / 'alpine/usr/lib') + ':' + wsl_path(LOCAL / 'toolchain/lib')
    binary = wsl_path(LOCAL / 'qmldiff-target-musl/debug/qmldiff')
    return subprocess.run(['wsl', '-d', 'Ubuntu', '--', musl, '--library-path', libs, binary, *args],
                          capture_output=True, text=True, timeout=300)


def apply(source_root, qmd_paths, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = engine('apply-diffs', wsl_path(source_root), wsl_path(dest), *[wsl_path(q) for q in qmd_paths])
    written = {}
    for match in re.finditer(r'Written file (\S+) - (\d+) diff\(s\) applied', result.stdout):
        written[match.group(1)] = int(match.group(2))
    return result, written


def require_owner_local(*extra):
    """Skip unless the owner's extracted rM2 resources and the local QMLDiff engine exist.

    Neither is redistributable/published: resources come from your own tablet via
    tools/extract_resources.py, the engine from https://github.com/asivery/qmldiff.
    """
    needed = [FIXTURES / rel for rel in PINNED] + [LOCAL / 'qmldiff-target-musl/debug/qmldiff'] + list(extra)
    missing = [str(p) for p in needed if not Path(p).exists()]
    if missing:
        raise unittest.SkipTest('owner-local fixture/toolchain absent: ' + missing[0])


def tmpdir():
    TMP_PARENT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TMP_PARENT)


def copy_sources(dest_root, mutate=None):
    """Copy the three pinned fixtures into dest_root; mutate is {relpath: (old, new)}."""
    for rel in PINNED:
        target = Path(dest_root) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (FIXTURES / rel).read_text(encoding='utf-8')
        if mutate and rel in mutate:
            old, new = mutate[rel]
            assert text.count(old) == 1, 'test mutation anchor must be unique: ' + old
            text = text.replace(old, new)
        target.write_text(text, encoding='utf-8', newline='\n')


NOOP_QMD = ''.join(
    'AFFECT /' + rel + '\n    TRAVERSE ' + root + '\n    END TRAVERSE\nEND AFFECT\n\n'
    for rel, root in ((DSV, 'FocusScope'), (SVG, 'TouchArea'), (DV, 'FocusScope')))


# --------------------------------------------------------------------------
# Qt helpers (qmlformat = Qt QML parser, QJSEngine = Qt JS engine)
# --------------------------------------------------------------------------

def qt_tool(name):
    try:
        import PySide6
    except ImportError:
        return None
    exe = Path(PySide6.__file__).parent / (name + ('.exe' if os.name == 'nt' else ''))
    return exe if exe.exists() else None


def qmlformat(path):
    tool = qt_tool('qmlformat')
    if tool is None:
        raise unittest.SkipTest('PySide6 qmlformat unavailable; run under uvx --from pyside6-essentials')
    result = subprocess.run([str(tool), str(path)], capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        raise AssertionError(f'Qt QML parser rejected {path}:\n{result.stderr}{result.stdout}')
    return result.stdout


_APP = None


def js_engine():
    global _APP
    try:
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtQml import QJSEngine
    except ImportError:
        raise unittest.SkipTest('PySide6 unavailable; run under uvx --from pyside6-essentials')
    _APP = QCoreApplication.instance() or QCoreApplication([])
    return QJSEngine()


def js(code):
    engine_ = js_engine()
    value = engine_.evaluate(code)
    if value.isError():
        raise AssertionError('QJSEngine error: ' + value.toString() + '\n' + code)
    return value.toVariant()


# --------------------------------------------------------------------------
# Formatted-QML structure helpers
# --------------------------------------------------------------------------

OBJECT_HEADER = re.compile(r'^(?:[\w.]+\s*:\s*)?([A-Z][\w.]*)\s*\{$')


def annotate(text):
    """Yield (stripped_line, path) where path = tuple of 'Type#id' for enclosing QML objects."""
    stack = []  # entries: [indent, Type or None (JS block), id]
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        while stack and line.startswith('}') and stack[-1][0] >= indent:
            stack.pop()
            break
        path = tuple(f'{t}#{i}' for _, t, i in stack if t)
        if line.startswith('id:') and stack and stack[-1][1]:
            stack[-1][2] = line.split(':', 1)[1].strip()
            path = tuple(f'{t}#{i}' for _, t, i in stack if t)
        out.append((line, path))
        if line.endswith('{'):
            header = OBJECT_HEADER.match(line)
            stack.append([indent, header.group(1) if header else None, ''])
    return out


def changes(base_text, patched_text):
    """Real-parser canonical diff: list of (path, removed_lines, added_lines)."""
    base = annotate(base_text)
    patched = annotate(patched_text)
    matcher = difflib.SequenceMatcher(None, [l for l, _ in base], [l for l, _ in patched], autojunk=False)
    result = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        path = patched[j1][1] if j1 < j2 else base[i1][1]
        result.append((path, [l for l, _ in base[i1:i2]], [l for l, _ in patched[j1:j2]]))
    return result


def squash(text):
    return re.sub(r'\s+', '', text)


def binding(text, path_suffix, name):
    """Return the expression of `name:` (or `... property T name:`) inside the object at path_suffix."""
    for line, path in annotate(text):
        if path[-len(path_suffix):] != tuple(path_suffix):
            continue
        m = re.match(r'^(?:readonly\s+)?(?:property\s+[\w<>.]+\s+)?' + re.escape(name) + r'\s*:\s*(.+)$', line)
        if m:
            return m.group(1).rstrip(';')
    raise AssertionError(f'binding {name} not found at {path_suffix}')


def block(text, header_regex):
    """Return the full formatted text of the block whose header line matches header_regex."""
    lines = text.splitlines()
    for i, raw in enumerate(lines):
        if re.match(header_regex, raw.strip()):
            indent = len(raw) - len(raw.lstrip(' '))
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == '}' and len(lines[j]) - len(lines[j].lstrip(' ')) == indent:
                    return '\n'.join(lines[i:j + 1])
    raise AssertionError('block not found: ' + header_regex)


def function_body(text, name):
    src = block(text, r'function ' + name + r'\(\)\s*\{$')
    return src[src.index('{') + 1:src.rindex('}')]


# --------------------------------------------------------------------------
# Shared real-engine runs
# --------------------------------------------------------------------------

class Fixture:
    ready = False

    @classmethod
    def load(cls):
        if cls.ready:
            return
        require_owner_local()
        for rel, digest in PINNED.items():
            path = FIXTURES / rel
            if not path.exists():
                raise unittest.SkipTest('owner-local rM2 resources absent: ' + str(path))
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise AssertionError('fixture is not the reviewed 3.28.0.172 resource: ' + rel)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        with tmpdir() as work:
            work = Path(work)
            noop = work / 'noop.qmd'
            noop.write_text(NOOP_QMD, newline='\n')
            base_run, base_written = apply(FIXTURES, [noop], work / 'baseline')
            if base_run.returncode != 0 or len(base_written) != 3:
                raise AssertionError('engine baseline failed:\n' + base_run.stdout + base_run.stderr)
            cls.patch_run, cls.patch_written = apply(FIXTURES, [QMD], work / 'patched')
            cls.raw = {}
            cls.base = {}
            cls.patched = {}
            for rel in PINNED:
                base_file = work / 'baseline' / rel
                cls.base[rel] = qmlformat(base_file)
                patched_file = work / 'patched' / rel
                if rel in PATCHED and cls.patch_run.returncode == 0 and patched_file.exists():
                    cls.raw[rel] = patched_file.read_text(encoding='utf-8')
                    cls.patched[rel] = qmlformat(patched_file)
                    keep = OUTPUT / rel
                    keep.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(patched_file, keep)
        cls.ready = True

    @classmethod
    def require_patch(cls, test):
        cls.load()
        if cls.patch_run.returncode != 0 or len(cls.patched) != len(PATCHED):
            test.fail('real QMLDiff engine did not apply src/infiniteCanvas.qmd:\n'
                      + cls.patch_run.stdout[-3000:] + cls.patch_run.stderr[-3000:])


def nip_expr():
    return binding(Fixture.patched[DSV], ('FocusScope#root',), 'nativeInfinitePage')


# Stand-in enum values: only equality matters to the patched logic.
DOCUMENT_ENUM = '{Notebook: 11, Pdf: 22, Ebook: 33}'


def eval_nip(file_type, note_page, has_document=True):
    document = f'{{fileType: Document.{file_type}}}' if has_document else 'null'
    return js(f'(function(){{ var Document = {DOCUMENT_ENUM}; var document = {document};'
              f' var notePage = {str(note_page).lower()}; return ({nip_expr()}); }})()')


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

class PatchSourceTest(unittest.TestCase):
    def test_qmd_is_version_gated_attributed_and_scoped_to_two_resources(self):
        self.assertTrue(QMD.exists(), 'src/infiniteCanvas.qmd missing')
        text = QMD.read_text(encoding='utf-8')
        statements = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith(';')]
        self.assertEqual(statements[0], 'VERSION ' + FIRMWARE, 'VERSION must be the first statement')
        self.assertEqual([s for s in statements if s.startswith('VERSION')], ['VERSION ' + FIRMWARE])
        affects = sorted(s.split()[1] for s in statements if s.startswith('AFFECT'))
        self.assertEqual(affects, sorted('/' + rel for rel in PATCHED))
        self.assertNotIn('LOAD', [s.split()[0] for s in statements])
        self.assertIn('MIT License', text)
        self.assertIn('Copyright (c) 2026 bahadrdsr', text)
        self.assertNotIn('CanvasSettings', text, 'no settings singleton / C++ dependency')
        self.assertNotIn('import InfiniteHorizontal', text)


class EngineApplyTest(unittest.TestCase):
    def setUp(self):
        Fixture.require_patch(self)

    def test_real_engine_writes_exactly_the_two_editor_resources(self):
        names = sorted(Path(p).name for p in Fixture.patch_written)
        self.assertEqual(names, ['DeviceSceneView.qml', 'DocumentView.qml'])
        self.assertTrue(all(n >= 1 for n in Fixture.patch_written.values()))
        self.assertNotIn('blocked', Fixture.patch_run.stderr)
        self.assertNotIn('Warning', Fixture.patch_run.stdout)

    def test_emitted_qml_is_accepted_by_qt_parser(self):
        for rel in PATCHED:
            self.assertIn('nativeInfinitePage', Fixture.patched[rel], rel)

    def test_device_scene_view_changes_are_exactly_the_intended_set(self):
        got = changes(Fixture.base[DSV], Fixture.patched[DSV])
        self.assertEqual(len(got), 6, got)
        inserted = got[0]
        self.assertEqual(inserted[0], ('FocusScope#root',))
        self.assertEqual(inserted[1], [])
        self.assertEqual([squash(l) for l in inserted[2]],
                         [squash('readonly property bool nativeInfinitePage: !!document && '
                                 'document.fileType === Document.Notebook && notePage')])
        # inserted directly after `property Document document`
        lines = [l for l, _ in annotate(Fixture.patched[DSV])]
        self.assertEqual(lines[lines.index(inserted[2][0]) - 1], 'property Document document')
        path, removed, added = got[1]
        self.assertEqual(path, ('FocusScope#root', 'Component#sceneViewComponent', 'SceneView#view'))
        self.assertEqual(removed, ['limitScrollingToPaper: true'])
        self.assertEqual([squash(a) for a in added], [squash('limitScrollingToPaper: !root.nativeInfinitePage')])
        for (path, removed, added), edge in zip(got[2:], ('left', 'right', 'top', 'bottom')):
            self.assertEqual(path, ('FocusScope#root', 'Item#', 'Item#uiOverlay', f'Rectangle#{edge}Overlay'))
            self.assertEqual(removed, [f'property real size: root.{edge}ViewportEdge'])
            self.assertEqual([squash(a) for a in added],
                             [squash(f'property real size: root.nativeInfinitePage ? 0 : root.{edge}ViewportEdge')])

    def test_scene_view_gestures_is_not_patched_so_page_swipes_stay_stock(self):
        self.assertNotIn('SceneViewGestures.qml', ' '.join(Fixture.patch_written))
        self.assertNotIn('SceneViewGestures', QMD.read_text(encoding='utf-8').split('AFFECT', 1)[1])

    def test_document_view_change_is_only_horizontal_snap(self):
        got = changes(Fixture.base[DV], Fixture.patched[DV])
        self.assertEqual([c[0] for c in got], [('FocusScope#root', 'DeviceSceneView#sceneView')], got)
        self.assertEqual(got[0][1], ['snapEnabled: !adjustViewPopup.active'])
        self.assertEqual([squash(a) for a in got[0][2]],
                         [squash('snapEnabled: !adjustViewPopup.active && !sceneView.nativeInfinitePage')])
        for name in ('moveForward', 'moveBackward'):
            self.assertEqual(function_body(Fixture.patched[DV], name), function_body(Fixture.base[DV], name), name)
        self.assertEqual(block(Fixture.patched[DV], r'NewPageButton \{'), block(Fixture.base[DV], r'NewPageButton \{'))

    def test_native_ink_render_save_and_vertical_gesture_code_is_untouched(self):
        dsv_blocks = [r'ScenePenInputHandler \{', r'PenInputSurface \{', r'ScreenDriver \{',
                      r'DeviceSceneViewBehavior \{', r'function scrollDown\(\)', r'function scrollUp\(\)',
                      r'function beginDragAndZoom\(\)', r'function updateDragAndZoom\(',
                      r'function endDragAndZoom\(\)', r'function updateViewportEdges\(\)']
        for header in dsv_blocks:
            self.assertEqual(block(Fixture.patched[DSV], header), block(Fixture.base[DSV], header), header)
        for header in (r'function openPage\(page, position\)', r'function openOverview\(\)',
                       r'function _saveScrollPosition\(\)', r'Pages \{', r'DocumentPageSlider \{'):
            self.assertEqual(block(Fixture.patched[DV], header), block(Fixture.base[DV], header), header)


class QtBehaviourTest(unittest.TestCase):
    def setUp(self):
        Fixture.require_patch(self)

    def test_native_infinite_page_only_for_notebook_note_pages(self):
        self.assertIs(eval_nip('Notebook', True), True)
        self.assertIs(eval_nip('Notebook', False), False)
        self.assertIs(eval_nip('Pdf', True), False, 'notebook pages inserted in PDF stay paged')
        self.assertIs(eval_nip('Pdf', False), False)
        self.assertIs(eval_nip('Ebook', False), False)
        self.assertIs(eval_nip('Ebook', True), False)
        self.assertIs(eval_nip('Notebook', True, has_document=False), False)

    def scene_bindings(self, nip):
        root = f'{{nativeInfinitePage: {str(nip).lower()}, leftViewportEdge: 7, rightViewportEdge: 8,' \
               ' topViewportEdge: 9, bottomViewportEdge: 10}'
        values = {}
        values['limit'] = js(f'(function(){{var root={root}; return ('
                             + binding(Fixture.patched[DSV], ('SceneView#view',), 'limitScrollingToPaper') + ');})()')
        for edge in ('left', 'right', 'top', 'bottom'):
            values[edge] = js(f'(function(){{var root={root}; return ('
                              + binding(Fixture.patched[DSV], (f'Rectangle#{edge}Overlay',), 'size') + ');})()')
        return values

    def docview_bindings(self, nip, adjust_active, new_page_visible):
        scope = f'var sceneView={{nativeInfinitePage:{str(nip).lower()}}};' \
                f' var adjustViewPopup={{active:{str(adjust_active).lower()}}};' \
                f' var newPageVisible={str(new_page_visible).lower()};'
        snap = binding(Fixture.patched[DV], ('DeviceSceneView#sceneView',), 'snapEnabled')
        visible = binding(Fixture.patched[DV], ('NewPageButton#newPageButton',), 'visible')
        return (js(f'(function(){{{scope} return ({snap});}})()'),
                js(f'(function(){{{scope} return ({visible});}})()'))

    def test_infinite_notebook_relaxes_paper_limit_hides_overlays_and_page_ui(self):
        v = self.scene_bindings(True)
        self.assertIs(v['limit'], False)
        self.assertEqual([v[e] for e in ('left', 'right', 'top', 'bottom')], [0, 0, 0, 0])
        # snap off; native new-page confirm button still shown when requested
        self.assertEqual(self.docview_bindings(True, False, True), (False, True))
        self.assertEqual(self.docview_bindings(True, False, False), (False, False))

    def test_pdf_ebook_and_paged_branch_keep_stock_values(self):
        for file_type, note in (('Pdf', True), ('Pdf', False), ('Ebook', False), ('Notebook', False)):
            nip = eval_nip(file_type, note)
            v = self.scene_bindings(nip)
            self.assertIs(v['limit'], True, file_type)
            self.assertEqual([v[e] for e in ('left', 'right', 'top', 'bottom')], [7, 8, 9, 10])
            for adjust in (False, True):
                for npv in (False, True):
                    self.assertEqual(self.docview_bindings(nip, adjust, npv), (not adjust, npv))

    def run_move(self, text, name, nip, current, count, new_page_visible=False, free=True):
        body = function_body(text, name)
        program = f'''(function() {{
            var log = [];
            var root = {{
                currentPage: {current}, newPageVisible: {str(new_page_visible).lower()},
                document: {{pageCount: {count}, isExporting: false}},
                sceneView: {{nativeInfinitePage: {str(nip).lower()}}},
                retailIntroLoader: {{active: false, resetDocument: function() {{ log.push('retail'); }}}},
                pageLabelTimer: {{restart: function() {{ log.push('label'); }}}},
                SystemMonitor: {{enoughFreeSpaceForCreating: {str(free).lower()}}},
                DocumentView: {{ScrollPosition: {{Save: 0, Restore: 1, SaveAndRestore: 2}}}},
                exitTextMode: function() {{ log.push('exitText'); }},
                openPage: function(p, pos) {{ log.push('open:' + p + ':' + pos); }},
                addPage: function() {{ log.push('add'); }},
                reportPageAdded: function() {{ log.push('report'); }},
                notifyPageExportWarning: function() {{ log.push('exportWarn'); }}
            }};
            root.root = root;
            with (root) {{ (function() {{ {body} }})(); }}
            return JSON.stringify({{log: log, newPageVisible: root.newPageVisible}});
        }})()'''
        import json
        return json.loads(js(program))

    def test_infinite_notebook_swipe_turns_pages_and_offers_new_page_like_stock(self):
        self.assertEqual(self.run_move(Fixture.patched[DV], 'moveForward', True, 0, 3)['log'], ['exitText', 'open:1:2'])
        self.assertEqual(self.run_move(Fixture.patched[DV], 'moveBackward', True, 1, 3)['log'], ['exitText', 'open:0:2'])
        self.assertEqual(self.run_move(Fixture.patched[DV], 'moveForward', True, 2, 3),
                         {'log': ['label'], 'newPageVisible': True})
        self.assertEqual(self.run_move(Fixture.patched[DV], 'moveForward', True, 2, 3, new_page_visible=True)['log'],
                         ['add', 'report'])

    def test_move_functions_match_stock_behaviour_when_not_infinite(self):
        cases = [('moveForward', 0, 3, False, True), ('moveForward', 2, 3, False, True),
                 ('moveForward', 2, 3, True, True), ('moveForward', 2, 3, False, False),
                 ('moveBackward', 1, 3, False, True), ('moveBackward', 0, 3, False, True)]
        for name, current, count, npv, free in cases:
            stock = self.run_move(Fixture.base[DV], name, False, current, count, npv, free)
            patched = self.run_move(Fixture.patched[DV], name, False, current, count, npv, free)
            self.assertEqual(patched, stock, (name, current, npv, free))
        # sanity: stock path really turns pages / offers a new page
        self.assertEqual(self.run_move(Fixture.base[DV], 'moveForward', False, 0, 3)['log'],
                         ['exitText', 'open:1:2'])
        self.assertEqual(self.run_move(Fixture.base[DV], 'moveForward', False, 2, 3),
                         {'log': ['label'], 'newPageVisible': True})


class FailClosedTest(unittest.TestCase):
    """Unexpected firmware anchors must make the real engine fail, not silently half-apply."""

    def setUp(self):
        Fixture.require_patch(self)

    def assert_engine_rejects(self, rel, old, new):
        with tmpdir() as work:
            work = Path(work)
            copy_sources(work / 'src', {rel: (old, new)})
            result, written = apply(work / 'src', [QMD], work / 'out')
            self.assertNotEqual(result.returncode, 0, f'engine accepted mutated anchor {old!r}:\n{result.stdout}')
            self.assertEqual(written.get(wsl_path(work / 'out') + '/' + rel), None)

    def test_rejects_changed_paper_limit_anchor(self):
        self.assert_engine_rejects(DSV, 'limitScrollingToPaper: true', 'limitScrollingToPaper: false')

    def test_rejects_changed_overlay_anchor(self):
        self.assert_engine_rejects(DSV, 'property real size: root.topViewportEdge',
                                   'property real size: root.topViewportEdge + 1')

    def test_rejects_missing_document_property(self):
        self.assert_engine_rejects(DSV, '    property Document document\n', '    property var doc\n')

    def test_rejects_changed_snap_anchor(self):
        self.assert_engine_rejects(DV, 'snapEnabled: !adjustViewPopup.active', 'snapEnabled: true')

    def test_stock_resources_still_apply(self):
        with tmpdir() as work:
            work = Path(work)
            copy_sources(work / 'src')
            result, written = apply(work / 'src', [QMD], work / 'out')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(written), len(PATCHED))


class VersionGateTest(unittest.TestCase):
    def setUp(self):
        Fixture.require_patch(self)

    def test_other_firmware_version_blocks_every_change(self):
        text = QMD.read_text(encoding='utf-8')
        with tmpdir() as work:
            work = Path(work)
            other = work / 'infiniteCanvas.qmd'
            other.write_text(text.replace('VERSION ' + FIRMWARE, 'VERSION 3.28.0.999', 1), newline='\n')
            result, written = apply(FIXTURES, [other], work / 'out')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(written, {}, 'no resource may be rewritten on another firmware')
            self.assertIn('blocked due to version mismatch', result.stderr)


def read_hashtab(path):
    data = Path(path).read_bytes()
    table, offset = {}, 0
    while offset + 12 <= len(data):
        key, size = struct.unpack_from('>QI', data, offset)
        offset += 12
        table[key] = data[offset:offset + size].decode('utf-8', 'replace')
        offset += size
    return table


class HashedPackageTest(unittest.TestCase):
    """The tablet consumes hashed QMD; hashing with the tablet hashtab must preserve semantics."""

    def setUp(self):
        if not HASHTAB.exists():
            self.skipTest('owner-local tablet hashtab absent')
        Fixture.require_patch(self)

    def test_hashtab_is_for_target_firmware(self):
        table = read_hashtab(HASHTAB)
        self.assertEqual(table.get(17607111715072197239), FIRMWARE)

    def test_hashed_qmd_round_trips_through_real_engine(self):
        table = read_hashtab(HASHTAB)
        with tmpdir() as work:
            work = Path(work)
            hashed = work / 'infiniteCanvas.qmd'
            shutil.copyfile(QMD, hashed)
            result = engine('hash-diffs', wsl_path(HASHTAB), wsl_path(hashed))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            hashed_text = hashed.read_text(encoding='utf-8')
            self.assertNotEqual(hashed_text, QMD.read_text(encoding='utf-8'))
            for rel in PATCHED:
                self.assertNotIn(rel, hashed_text, 'resource paths must be hashed with the tablet table')
            self.assertIn('VERSION ' + FIRMWARE, hashed_text)
            # Resolve hashes back with the tablet table, then apply with the real engine.
            def unhash_ids(m):
                return '.'.join(table[int(h)] for h in m.group(1).split('.'))
            resolved = re.sub(r'~&(\d+)&~', lambda m: table[int(m.group(1))], hashed_text)
            resolved = re.sub(r'\[\[(["\'`])(\d+)\]\]', lambda m: m.group(1) + table[int(m.group(2))] + m.group(1),
                              resolved)
            resolved = re.sub(r'\[\[([\d.]+)\]\]', unhash_ids, resolved)
            self.assertNotIn('[[', resolved)
            restored = work / 'restored.qmd'
            restored.write_text(resolved, newline='\n')
            run, written = apply(FIXTURES, [restored], work / 'out')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            for rel in PATCHED:
                self.assertEqual((work / 'out' / rel).read_text(encoding='utf-8'), Fixture.raw[rel], rel)


class PreflightToolTest(unittest.TestCase):
    def test_preflight_accepts_reviewed_resources_and_rejects_others(self):
        if not all((FIXTURES / rel).exists() for rel in PINNED):
            self.skipTest('owner-local rM2 resources absent')
        from tools.preflight import check
        self.assertEqual(check(FIXTURES), [])
        with tmpdir() as work:
            work = Path(work)
            copy_sources(work, {DV: ('visible: newPageVisible\n', 'visible: true\n')})
            errors = check(work)
            self.assertEqual(len(errors), 1)
            self.assertIn('DocumentView.qml', errors[0])
            (work / SVG).unlink()
            self.assertEqual(len(check(work)), 2)


if __name__ == '__main__':
    unittest.main()
