import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ResourcesTest(unittest.TestCase):
    def test_extracts_real_tablet_document_resources_without_device_execution(self):
        binary = ROOT / '.local/device/xochitl'
        if not binary.exists():
            self.skipTest('copy /usr/bin/xochitl from your own rM2 to .local/device/xochitl')
        from tools.extract_resources import extract
        resources = extract(binary)
        path = '/qml/device/view/documentview/DeviceSceneView.qml'
        self.assertIn(path, resources)
        self.assertIn(b'limitScrollingToPaper: true', resources[path])
        self.assertIn(b'id: nextPageGesture', resources['/qml/device/view/documentview/SceneViewGestures.qml'])


if __name__ == '__main__':
    unittest.main()
