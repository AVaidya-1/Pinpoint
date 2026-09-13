"""Regression checks for the extraction's configurable Git destination."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('team_git', Path(__file__).parents[1] / 'team_git.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        module.ROOT = Path(self.temp.name)

    def configure(self, remote):
        (module.ROOT / 'orchestration.json').write_text(json.dumps({'expected_remote':remote}))

    def test_placeholder_refuses_dispatch(self):
        self.configure('https://github.com/OWNER/PRODUCT.git')
        with self.assertRaises(RuntimeError):
            module.expected_remote()

    def test_backup_requires_exact_configured_remote(self):
        self.configure('https://github.com/example/new-product.git')
        policy = module.ROOT / 'out/orchestration/runtime/github-backup.json'
        policy.parent.mkdir(parents=True)
        policy.write_text(json.dumps({'approved':True,'remote':'https://github.com/example/old-product.git'}))
        with self.assertRaises(RuntimeError):
            module.require_backup_approval()
        policy.write_text(json.dumps({'approved':True,'remote':module.expected_remote()}))
        module.require_backup_approval()

if __name__ == '__main__':
    unittest.main()
