"""Real QMLDiff sidebar Home integration; native reset only, no scrolling changes."""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('home_harness', ROOT / 'tests/test_canvas_patch.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
TOOLBAR = 'qt/qml/xofm/libs/toolbar/qml/Toolbar.qml'


class HomeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        h.require_owner_local(h.FIXTURES / TOOLBAR)
        dest = ROOT / '.local/home-test-output'
        result, _ = h.apply(h.FIXTURES,
            [ROOT / 'src/infiniteCanvas.qmd', ROOT / 'src/infiniteCanvasHome.qmd'], dest)
        if result.returncode:
            raise AssertionError(result.stdout[-2000:] + result.stderr[-2000:])
        cls.toolbar = h.qmlformat(dest / TOOLBAR)
        cls.document = h.qmlformat(dest / h.DV)
        block = h.block(cls.document, r'onCanvasHomeSelected:\s*\{')
        cls.callback = block[block.index('{') + 1:block.rindex('}')]

    def test_home_is_inside_native_sidebar_grid_not_a_floating_overlay(self):
        self.assertIn('objectName: "infiniteCanvasHome"', self.toolbar)
        paths = [path for line,path in h.annotate(self.toolbar)
                 if line == 'objectName: "infiniteCanvasHome"']
        self.assertEqual(len(paths),1)
        self.assertIn('GridLayout#toolLayout',paths[0])
        self.assertIn('Item#toolbar',paths[0])
        self.assertEqual(paths[0][-1], 'ArkControls.ToolButton#canvasHomeButton')
        self.assertNotIn('infiniteCanvasHome', self.document)
        self.assertIn('canvasHomeSelected()',h.binding(self.toolbar,
            ('ArkControls.ToolButton#canvasHomeButton',),'onClicked'))

    def test_sidebar_button_hides_when_collapsed_or_outside_notebooks(self):
        expr = h.binding(self.toolbar,('ArkControls.ToolButton#canvasHomeButton',),'visible')
        for expanded,available in [(False,False),(False,True),(True,False),(True,True)]:
            actual = h.js('(function(){var root={expanded:'+str(expanded).lower()+
                ',canvasHomeAvailable:'+str(available).lower()+'};return '+expr+';})()')
            self.assertEqual(actual,expanded and available)
        availability = h.binding(self.document,('Toolbar#toolbar',),'canvasHomeAvailable')
        self.assertIn('nativeInfinitePage',availability)
        self.assertIn('canvasHomeAvailable',self.toolbar)

    def test_home_uses_house_icon_instead_of_text(self):
        self.assertNotIn('qsTr("Home")', self.toolbar)
        self.assertIn('qrc:/qml/images/house.svg', self.toolbar)

    def test_tablet_build_avoids_unavailable_accessibility_attached_type(self):
        # Native 3.28 rM2 Qt rejects Accessible.name at component creation.
        # qmlformat parsing alone does not detect this target-build restriction.
        self.assertNotIn('Accessible.name', self.toolbar)

    def test_callback_uses_native_original_view_and_does_not_modify_ink(self):
        result = h.js(("""(function(){
            var resets=0;var updates=0;var ink=[{x:8000,y:12000}];
            var sceneView={resetViewport:function(){resets++;},
                           updateScrollbars:function(){updates++;}};
            function click(){CALLBACK}
            click();return {resets:resets,updates:updates,ink:ink};
        })()""").replace('CALLBACK',self.callback))
        self.assertEqual(result['resets'],1)
        self.assertEqual(result['updates'],1)
        self.assertEqual(result['ink'],[{'x':8000,'y':12000}])
        self.assertNotIn('setFocalPoint',self.callback)
        self.assertNotIn('boundingRect',self.callback)
        self.assertNotIn('clear',self.callback.lower())


if __name__ == '__main__':
    unittest.main()
