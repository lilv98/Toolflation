# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""Grok 4.6 in Grok Build, xAI's command-line agent, in headless mode on Vertex AI.

Grok Build keeps its own system prompt; its built-in tools and subagents are off, its scans of other vendors' settings
are off, and the market's MCP tools, which it lists through its own search_tool and use_tool, are the only tools it may
call. Each run gets a fresh GROK_HOME with the model and the market in its config.toml. Requests pass through a local
relay that adds the Vertex token, waits out rate limits and drops the keep-alive lines of the event stream."""
import asyncio
import http.server
import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import google.auth
import google.auth.transport.requests
import requests

from .. import credentials
from . import parse, retry

MODEL = dict(model='xai/grok-4.6', location='global', effort='low')
MAX_TURNS = 12
RETRIES = 20  # the relay waits out this many rate limits per request
GROK = shutil.which('grok') or str(Path(os.sys.executable).parent / 'grok')
CONFIG = """[model.vertex]
model = "{model}"
base_url = "{relay}/v1/projects/{project}/locations/{location}/endpoints/openapi"
api_key = "relay"
context_window = 256000

[mcp_servers.market]
command = {command}
args = {args}
env = {env}

[features]
telemetry = "off"

[compat.claude]
agents = false
hooks = false
mcps = false
rules = false
skills = false

[compat.cursor]
agents = false
hooks = false
mcps = false
rules = false
skills = false

[compat.codex]
hooks = false
skills = false
"""
VERTEX = 'https://aiplatform.googleapis.com'
_credentials, _lock, _relay = None, threading.Lock(), None


def token():
    global _credentials
    with _lock:
        _credentials = _credentials or google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])[0]
        if not _credentials.valid:
            _credentials.refresh(google.auth.transport.requests.Request())
        return _credentials.token


class Relay(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        for attempt in range(RETRIES):  # wait out rate limits here
            upstream = requests.post(VERTEX + self.path, data=body, stream=True, timeout=900,
                                     headers={'Authorization': f'Bearer {token()}', 'Content-Type': 'application/json'})
            if upstream.status_code != 429:
                break
            upstream.close()
            time.sleep(min(60, 5 * 2 ** attempt))
        with upstream:
            self.send_response(upstream.status_code)
            self.send_header('Content-Type', upstream.headers.get('Content-Type', 'application/json'))
            self.end_headers()
            try:
                for line in upstream.iter_lines():
                    if line != b'data: : keepalive':
                        self.wfile.write(line + b'\n')
                        self.wfile.flush()
            except BrokenPipeError:  # Grok Build closes the stream once it has the final event
                pass

    def log_message(self, *args):
        pass


def relay():
    """Start the relay once per process; returns its base URL."""
    global _relay
    if not _relay:
        _relay = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Relay)
        threading.Thread(target=_relay.serve_forever, daemon=True).start()
    return f'http://127.0.0.1:{_relay.server_port}'


def toml(value):
    """TOML inline value for a string, list of strings or flat string table (JSON strings are valid TOML strings)."""
    if isinstance(value, dict):
        return '{ ' + ', '.join(f'{json.dumps(k)} = {json.dumps(v)}' for k, v in value.items()) + ' }'
    return json.dumps(value)


async def chat(directory, prompt, mcp, schema=None, timeout=900):
    """A failed run (stream timeout, quota) is retried from scratch."""
    started = time.monotonic()
    record = await retry(lambda: run(prompt, mcp, timeout), attempts=3)
    if schema:
        record['structured'] = parse(record, schema)
    return {**record, 'seconds': time.monotonic() - started}


async def run(prompt, mcp, timeout):
    home = Path(tempfile.mkdtemp(prefix='toolflation-grok-'))
    (home / 'config.toml').write_text(CONFIG.format(**MODEL, project=credentials.project(), relay=relay(), command=toml(mcp['command']),
                                                    args=toml(mcp['args']), env=toml(mcp['env'])))
    command = [GROK, '-p', prompt, '-m', 'vertex', '--effort', MODEL['effort'], '--max-turns', str(MAX_TURNS),
               '--output-format', 'streaming-messages-json', '--tools', 'search_tool,use_tool', '--disallowed-tools', 'Agent',
               '--allow', 'MCPTool(market__*)', '--cwd', str(home), '--no-auto-update']
    record, history, process = {}, [], None
    try:
        process = await asyncio.create_subprocess_exec(*command, cwd=home, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                       env={**os.environ, 'GROK_HOME': str(home)})
        async with asyncio.timeout(timeout):
            stdout, stderr = await process.communicate()
        for line in stdout.decode().splitlines():
            event = json.loads(line) if line.startswith('{') else None
            if event and event.get('type') == 'result':
                record.update(text=event.get('result') or '', stop_reason=event.get('stop_reason') or event.get('subtype'), usage=event.get('usage'))
                if event.get('is_error'):
                    record['error'] = event.get('subtype') or 'error'
            elif event:
                history.append(event)
        if process.returncode or 'text' not in record:
            record.setdefault('error', f'exit {process.returncode}: {stderr.decode()[-500:]}')
    except Exception as error:
        record['error'] = f'{type(error).__name__}: {error}'
        if process and process.returncode is None:
            process.kill()
    shutil.rmtree(home, ignore_errors=True)
    return {**record, 'history': history}
