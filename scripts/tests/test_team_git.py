import importlib.util
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location('team_git', Path(__file__).parents[1] / 'team_git.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GitSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        module.ROOT = Path(self.temp.name)
        module.git('init', '-b', 'codex/test')
        module.git('config', 'user.email', 'test@example.invalid')
        module.git('config', 'user.name', 'Local test')
        module.git('remote', 'add', 'origin', 'https://github.com/OWNER/PRODUCT.git')
        (module.ROOT / 'orchestration.json').write_text('{"expected_remote":"https://github.com/example/product.git"}')
        module.git('remote', 'set-url', 'origin', 'https://github.com/example/product.git')
        module.git('add', 'orchestration.json')
        (module.ROOT / 'readme.md').write_text('baseline')
        module.git('add', 'readme.md')
        module.git('commit', '-m', 'baseline')

    def test_checkpoint_preserves_source(self):
        (module.ROOT / 'readme.md').write_text('reviewed')
        module.checkpoint('Reviewed task: fixture')
        self.assertEqual(module.git('status', '--porcelain'), '')
        self.assertEqual(module.git('show', 'HEAD:readme.md'), 'reviewed')

    def test_product_text_sources_checkpoint(self):
        for name in ['view.tsx', 'api.ts', 'config.mjs', 'config.cjs', 'uv.lock', 'icon.svg', '.env.example']:
            (module.ROOT / name).write_text('')
        module.checkpoint('Product source types')
        self.assertEqual(module.git('status', '--porcelain'), '')

    def test_binary_and_credentials_remain_rejected(self):
        for name in ['fixture.png', 'original.pdf', '.env', '.env.local']:
            with self.subTest(name=name):
                path = module.ROOT / name
                path.write_text('not allowed')
                with self.assertRaises(RuntimeError):
                    module.checkpoint('must reject')
                self.assertEqual(module.git('diff', '--cached', '--name-only'), '')
                path.unlink()

    def test_main_rejected(self):
        module.git('switch', '-c', 'main')
        with self.assertRaises(RuntimeError):
            module.check_branch()

    def test_secret_rejected_before_staging(self):
        (module.ROOT / 'secret.txt').write_text('-----BEGIN RSA PRIVATE KEY-----')
        with self.assertRaises(RuntimeError):
            module.checkpoint('bad')
        self.assertEqual(module.git('diff', '--cached', '--name-only'), '')

    def test_existing_stage_rejected(self):
        (module.ROOT / 'readme.md').write_text('owner change')
        module.git('add', 'readme.md')
        with self.assertRaises(RuntimeError):
            module.checkpoint('bad')
        self.assertEqual(module.git('show', ':readme.md'), 'owner change')

    def test_deletion_needs_review(self):
        (module.ROOT / 'readme.md').unlink()
        with self.assertRaises(RuntimeError):
            module.checkpoint('bad')

    def test_wrong_remote_rejected(self):
        module.git('remote', 'set-url', 'origin', 'https://example.invalid/wrong')
        with self.assertRaises(RuntimeError):
            module.check_branch()

    def test_optional_backup_saves_locally_without_approval(self):
        script = module.ROOT / 'scripts' / 'team_git.py'
        script.parent.mkdir()
        script.write_text(Path(module.__file__).read_text(encoding='utf-8'), encoding='utf-8')
        module.git('add', 'scripts/team_git.py')
        module.git('commit', '-m', 'Install test harness')
        (module.ROOT / 'readme.md').write_text('reviewed task change')
        result = subprocess.run(
            [sys.executable, str(script), 'checkpoint', '--push-if-approved'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Local checkpoint only', result.stdout)
        self.assertEqual(module.git('status', '--porcelain'), '')

if __name__ == '__main__':
    unittest.main()
