"""Verify installed tablet QMDs compose with the new canvas patch."""
from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('canvas_tests', ROOT / 'tests/test_canvas_patch.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class CompositionTest(unittest.TestCase):
    def test_canvas_and_home_preserve_existing_patch_results_outside_four_resources(self):
        active = ROOT / '.local/active-patches'
        harness.require_owner_local(active / 'hashtab')
        output = ROOT / '.local/composition-output'
        baseline = ROOT / '.local/composition-baseline'
        table = active / 'hashtab'
        for dest, additions in ((baseline, []), (output, [ROOT / 'src/infiniteCanvas.qmd', ROOT / 'src/infiniteCanvasHome.qmd'])):
            result = harness.engine('apply-with-hashtab', harness.wsl_path(table),
                harness.wsl_path(harness.FIXTURES), harness.wsl_path(dest),
                *[harness.wsl_path(p) for p in sorted(active.glob('*.qmd'))],
                *[harness.wsl_path(p) for p in additions])
            self.assertEqual(result.returncode, 0, result.stdout[-5000:] + result.stderr[-5000:])
            self.assertNotIn('Failed', result.stdout + result.stderr)
        before = {p.relative_to(baseline).as_posix(): p.read_bytes()
                  for p in baseline.rglob('*.qml')}
        after = {p.relative_to(output).as_posix(): p.read_bytes()
                 for p in output.rglob('*.qml')}
        toolbar = 'qt/qml/xofm/libs/toolbar/qml/Toolbar.qml'
        expected = set(harness.PATCHED) | {toolbar}
        self.assertEqual(set(before) | expected, set(after))
        for path, data in before.items():
            if path not in expected:
                self.assertEqual(after[path], data, path)
        for path in harness.PATCHED:
            self.assertIn(b'nativeInfinitePage', after[path], path)
            harness.qmlformat(output / path)
        self.assertIn(b'infiniteCanvasHome', after[toolbar])
        harness.qmlformat(output / toolbar)
        print(f'Composition: {len(before)} existing resource outputs preserved; three canvas/sidebar resources parsed')


if __name__ == '__main__':
    unittest.main()
