"""Install the pinned OpenChatCut engine used by the AI Editor chat.

Run from the Cascade root: python3 scripts/install_openchatcut.py

Clones the audited commit into the git-ignored backend/editor/.cache/openchatcut
and installs its lockfile-pinned npm packages WITHOUT running package install
scripts. Cascade uses Homebrew/system ffmpeg+ffprobe and the installed Chrome,
so the skipped binary downloads are not needed. No accounts, keys, models or
paid services are involved. Requires Node 24, git, ffmpeg and Google Chrome.
"""
from pathlib import Path
import json
import subprocess

COMMIT = '7fa4b7903e7ebecf832a36249f0c0c755200cc17'  # OpenChatCut 0.2.17 (AGPL-3.0-or-later)
root = Path(__file__).resolve().parents[1]
target = root/'backend/editor/.cache/openchatcut'

if (target/'package.json').is_file():
    head = subprocess.run(['git', '-C', str(target), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    if head != COMMIT:
        raise SystemExit(f'Existing OpenChatCut at {target} is {head or "unknown"}, not the audited {COMMIT}. It was not overwritten.')
    print(f'Audited OpenChatCut already present at {target}.')
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init', str(target)], check=True)
    subprocess.run(['git', '-C', str(target), 'remote', 'add', 'origin', 'https://github.com/0xsline/OpenChatCut.git'], check=True)
    subprocess.run(['git', '-C', str(target), 'fetch', '--depth', '1', 'origin', COMMIT], check=True)
    subprocess.run(['git', '-C', str(target), 'checkout', COMMIT], check=True)

if 'GNU AFFERO GENERAL PUBLIC LICENSE' not in (target/'LICENSE').read_text()[:200]:
    raise SystemExit('Expected the AGPL-3.0 license; installation stopped.')
if json.loads((target/'package.json').read_text())['version'] != '0.2.17':
    raise SystemExit('Unexpected OpenChatCut version; installation stopped.')
if not (target/'node_modules/.bin/tsx').exists():
    subprocess.run(['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=target, check=True,
                   env={**__import__('os').environ, 'ELECTRON_SKIP_BINARY_DOWNLOAD': '1'})
print(f'OpenChatCut 0.2.17 ready at {target}. Package install scripts were not run.')
