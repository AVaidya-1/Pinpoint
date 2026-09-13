import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('team_app', Path(__file__).parents[1] / 'team_app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class AppLauncherTests(unittest.TestCase):
    def test_existing_dashboard_is_reused(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(app, 'ROOT', Path(folder)), \
             mock.patch.object(app, 'service_identity', return_value=True), \
             mock.patch.object(app, 'browser_command', return_value=['edge.exe','--app=http://127.0.0.1:8765']), \
             mock.patch.object(app.subprocess, 'Popen') as launch:
            self.assertEqual('http://127.0.0.1:8765', app.launch())
            self.assertEqual(1, launch.call_count)
            self.assertEqual('edge.exe', launch.call_args.args[0][0])

    def test_wrong_service_does_not_open_browser(self):
        process = mock.Mock()
        process.poll.return_value = 1
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(app, 'ROOT', Path(folder)), \
             mock.patch.object(app, 'service_identity', return_value=False), \
             mock.patch.object(app.subprocess, 'Popen', return_value=process), \
             mock.patch.object(app, 'browser_command') as browser:
            with self.assertRaises(RuntimeError):
                app.launch()
            browser.assert_not_called()

if __name__ == '__main__':
    unittest.main()
