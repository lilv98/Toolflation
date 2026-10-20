# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""DeepSeek V4.1 Flash in DeepSeek Harness, through its Python SDK, with the model served by OpenRouter.

The SDK runs the harness's own sdk profile, with its system prompt and agent loop. Its shell, file, web, skill, todo,
goal, workflow, plan-mode and subagent tools are off, and so are the uploads of session logs and plugin inventories to
DeepSeek and OpenTelemetry. Each chat gets a fresh DSH_HOME and an empty working directory."""
import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path

from deepseek_harness import DeepSeekHarness

from .. import credentials
from . import parse, retry

MODEL = dict(model='deepseek/deepseek-v4.1-flash', effort='low', base_url='https://openrouter.ai/api/v1')
OFF = ('tool-bash', 'tool-pwsh', 'tool-jobs', 'tool-fs', 'tool-fs-search', 'tool-skill', 'tool-subagent-control',
       'tool-subagent-list-agents', 'tool-subagent', 'tool-subagent-fork', 'tool-workflow', 'tool-todo', 'tool-goal',
       'tool-ralph', 'tool-web', 'plan-mode', 'session-log-deepseek', 'plugin-package-inventory-deepseek', 'session-telemetry-otel')


def patch(mcp):
    """Profile patch (JSON is valid YAML): built-in tools off, the market's MCP server on as mcp__market__*."""
    server = {'serverName': 'market', 'transport': 'stdio', **mcp, 'failOnStartupError': True}
    return [{'id': row, 'disabled': True} for row in OFF] + [{'insert': [{'id': 'mcp-market', 'name': '@deepseek-ai/dsh-mcp-client', 'config': server}]}]


def run(prompt, mcp, timeout):
    home, work = Path(tempfile.mkdtemp(prefix='toolflation-dsh-')), Path(tempfile.mkdtemp(prefix='toolflation-dsh-work-'))
    (home / 'market.patch.yml').write_text(json.dumps(patch(mcp)))
    key = credentials.key('openrouter')
    try:
        with DeepSeekHarness(dsh_home=str(home), cwd=str(work), runtime_cwd=str(work), provider='deepseek-official',
                             model=MODEL['model'], reasoning_effort=MODEL['effort'], base_url=MODEL['base_url'],
                             api_key=key if isinstance(key, str) else next(iter(key.values())),
                             patches=(str(home / 'market.patch.yml'),), request_timeout_seconds=timeout) as harness:
            result = harness.run(prompt, session_id='chat')
        return {'text': result.final_response or '', 'stop_reason': result.finish_reason, 'history': list(result.events),
                **({} if result.finish_reason == 'completed' else {'error': result.finish_reason or 'no turn ended'})}
    except Exception as error:
        return {'error': f'{type(error).__name__}: {error}', 'history': []}
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


async def chat(directory, prompt, mcp, schema=None, timeout=900):
    """A failed run is retried from scratch."""
    started = time.monotonic()
    record = await retry(lambda: asyncio.to_thread(run, prompt, mcp, timeout), attempts=3)
    if schema:
        record['structured'] = parse(record, schema)
    return {**record, 'seconds': time.monotonic() - started}
