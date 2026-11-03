"""Ask Claude through the local Claude Code CLI, signed in with the user's Claude subscription.

No API key is ever used: every Anthropic credential variable is removed from the child process,
so `claude -p` can only authenticate with the claude.ai (Pro/Max) sign-in and nothing is billed
per request. Frames are written to a private temporary folder and are the only files Claude may
read (tools: Read only). Set CASCADE_CLAUDE_BIN to use a specific `claude` binary.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException

API_VARIABLES = ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_CUSTOM_HEADERS',
                 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY')
LIMIT = re.compile(r'usage limit|rate limit|limit reached|out of (extra )?usage|resets? (at|in)', re.I)


class UsageLimit(HTTPException):
    def __init__(self, detail):
        super().__init__(429, detail)


def binary():
    for candidate in (os.environ.get('CASCADE_CLAUDE_BIN', ''), shutil.which('claude') or '',
                      str(Path.home()/'.local'/'claude-code'/'node_modules'/'.bin'/'claude')):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def subscription_env():
    env = {k: v for k, v in os.environ.items() if k not in API_VARIABLES}
    env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
    return env


def signed_in():
    """'pro'/'max'/… when the CLI is signed in with a Claude subscription, else ''."""
    claude = binary()
    if not claude: return ''
    try:
        status = json.loads(subprocess.run([claude, 'auth', 'status'], capture_output=True, text=True, timeout=20,
                                           env=subscription_env()).stdout or '{}')
    except (OSError, subprocess.SubprocessError, ValueError):
        return ''
    return (status.get('subscriptionType') or 'subscription') if status.get('loggedIn') and status.get('authMethod') == 'claude.ai' else ''


def _json(text):
    start = text.find('{')
    end = text.rfind('}')
    if start < 0 or end <= start: raise ValueError('Claude did not return JSON.')
    return json.loads(text[start:end+1])


def ask(system, prompt, images=(), timeout=300):
    """Parsed JSON object from Claude. `images` are (file name, JPEG bytes) pairs Claude can Read.
    Raises UsageLimit when the subscription's usage limit is reached, HTTPException(503) otherwise."""
    claude = binary()
    if not claude:
        raise HTTPException(503, 'Claude Code is not installed (npm install --prefix ~/.local/claude-code @anthropic-ai/claude-code).')
    if not signed_in():
        raise HTTPException(503, 'Claude Code is not signed in with a Claude subscription. Run `claude` once and choose /login.')
    with tempfile.TemporaryDirectory(prefix='cascade-claude-') as work:
        for name, data in images:
            (Path(work)/Path(name).name).write_bytes(data)
        listing = '\n'.join(f'- {Path(name).name}' for name, _ in images)
        task = prompt+(f'\n\nFrames in the current folder (open each with the Read tool before answering):\n{listing}' if images else '')
        try:
            run = subprocess.run([claude, '-p', task, '--output-format', 'json', '--append-system-prompt', system,
                                  '--tools', 'Read', '--allowedTools', 'Read', '--permission-mode', 'dontAsk',
                                  '--no-session-persistence', '--setting-sources', '', '--strict-mcp-config'],
                                 cwd=work, env=subscription_env(), capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, 'Claude took too long to plan this edit.') from None
        except OSError as exc:
            raise HTTPException(503, f'Could not start Claude Code: {exc}') from None
    try:
        outcome = json.loads(run.stdout)
    except ValueError:
        message = (run.stderr or run.stdout or 'no output')[-300:]
        if LIMIT.search(message): raise UsageLimit('Your Claude plan\'s usage limit is reached: '+message) from None
        raise HTTPException(503, 'Claude Code failed: '+message) from None
    result = str(outcome.get('result') or '')
    if outcome.get('is_error'):
        if LIMIT.search(result): raise UsageLimit('Your Claude plan\'s usage limit is reached. '+result[:200])
        raise HTTPException(503, 'Claude Code failed: '+result[:300])
    try:
        return _json(result)
    except ValueError:
        raise HTTPException(502, 'Claude answered without a usable storyboard.') from None
