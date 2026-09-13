"""Conservative Git checkpoints for the single-writer autonomous runner."""
import argparse
import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def expected_remote():
    config = json.loads((ROOT / 'orchestration.json').read_text(encoding='utf-8-sig'))
    remote = config.get('expected_remote', '')
    if not remote or remote == 'https://github.com/OWNER/PRODUCT.git':
        raise RuntimeError('Configure expected_remote in orchestration.json first.')
    return remote

def require_backup_approval():
    path = ROOT / 'out/orchestration/runtime/github-backup.json'
    if not path.exists():
        raise RuntimeError('GitHub backup awaits owner approval. No automatic upload is enabled.')
    policy = json.loads(path.read_text(encoding='utf-8-sig'))
    if policy.get('approved') is not True or policy.get('remote') != expected_remote():
        raise RuntimeError('GitHub backup approval does not match this repository.')

def git(*args):
    result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Git command failed')
    return result.stdout.strip()

def check_branch():
    branch = git('branch', '--show-current')
    if not branch.startswith('codex/'):
        raise RuntimeError('Autonomous work requires a codex/ branch. Main is never used.')
    if git('remote', 'get-url', 'origin') != expected_remote():
        raise RuntimeError('Unexpected GitHub destination; refusing to continue.')
    return branch

def checkpoint(label, push=False):
    branch = check_branch()
    if push:
        require_backup_approval()
    if git('diff', '--cached', '--name-only'):
        raise RuntimeError('Pre-staged changes require review; refusing to mix them into a checkpoint.')
    paths = git('ls-files', '--modified', '--others', '--exclude-standard', '-z').split('\0')
    paths = sorted(set(p for p in paths if p))
    # Keep uploads bounded to readable source and documentation. Submodules,
    # generated files, secrets and unfamiliar file types require human review.
    suffixes = {'.py', '.ps1', '.cmd', '.md', '.txt', '.json', '.html', '.css', '.js', '.toml', '.yml', '.yaml', '.ts', '.tsx', '.mjs', '.cjs', '.lock', '.svg'}
    for name in paths:
        path = ROOT / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise RuntimeError(f'Non-file, deletion or nested repository needs review: {name}')
        if path.suffix.lower() not in suffixes and name not in {'.gitignore', '.env.example'}:
            raise RuntimeError(f'File type needs review: {name}')
        if path.stat().st_size > 2_000_000:
            raise RuntimeError(f'Large file needs review: {name}')
        text = path.read_text(encoding='utf-8-sig')
        import re
        if re.search(r'-----BEGIN .*PRIVATE KEY-----|\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{24,})|ntfy\.sh/agent-orchestration-[a-f0-9]{32}', text):
            raise RuntimeError(f'Possible secret requires review: {name}')
    if paths:
        git('add', '--', *paths)
        git('commit', '-m', label)
    if push:
        git('push', '--set-upstream', 'origin', branch)
    print(git('rev-parse', '--short', 'HEAD'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check', 'checkpoint'])
    parser.add_argument('--label', default='Autonomous work checkpoint')
    parser.add_argument('--push', action='store_true')
    parser.add_argument('--push-if-approved', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'check':
            check_branch()
            if git('status', '--porcelain', '--untracked-files=normal'):
                raise RuntimeError('Uncommitted changes remain. Review/save the baseline before autonomous work.')
            print('Git baseline is clean; work branch verified.')
        else:
            push = args.push
            if args.push_if_approved and not push:
                try:
                    require_backup_approval()
                    push = True
                except RuntimeError:
                    print('Local checkpoint only; standing GitHub upload approval is not configured.')
            checkpoint(args.label, push)
    except (RuntimeError, OSError, UnicodeError) as error:
        parser.exit(1, f'Git safety stop: {error}\n')
