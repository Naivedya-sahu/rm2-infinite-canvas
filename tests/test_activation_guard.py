"""Classify real device startup logs without unrelated-mod false positives."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GuardTest(unittest.TestCase):
    def pattern(self):
        script = (ROOT / 'packaging/guarded-activation.sh').read_text()
        match = re.search(r"fatal_pattern='([^']+)'", script)
        if not match:
            match = re.search(r"grep -Eqi '([^']+)'", script)
        self.assertIsNotNone(match)
        return match.group(1)

    # Verbatim warnings from a healthy rM2 3.28.0.172 startup with other mods installed.
    UNRELATED_WARNINGS = (
        'qrc:/qml/device/view/experimental/Experimental.qml:71: ReferenceError: Values is not defined',
        "qrc:/qml/device/view/navigator/Navigator.qml:1128: TypeError: Cannot read property 'visible' of undefined",
        '[librarian]: QML helper error: <Unknown File>:3:9: module "xofm.libs.library" is not installed',
    )

    def test_real_startup_warnings_from_unrelated_mods_do_not_trigger_rollback(self):
        for line in self.UNRELATED_WARNINGS:
            self.assertIsNone(re.search(self.pattern(), line, re.I), line)

    def test_fatal_component_or_changed_resource_errors_trigger_recovery(self):
        for message in (
            'Toolbar.qml:782 Non-existent attached object',
            'Type Toolbar unavailable',
            'Cannot load legacydevice/window/main',
            'DocumentView.qml:2000: ReferenceError: sceneView is not defined',
            'Toolbar.qml:500: TypeError: Cannot read property',
        ):
            self.assertRegex(message, self.pattern())

    def test_rollback_disables_both_canvas_qmds_and_needs_build_dir(self):
        script = (ROOT / 'packaging/guarded-activation.sh').read_text()
        self.assertIn('for f in infiniteCanvas.qmd infiniteCanvasHome.qmd', script)
        self.assertIn('base=${1:?build dir required}', script)


if __name__ == '__main__':
    unittest.main()
