# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""GPT-5.6 Sol in Codex, through the local Codex app-server with a ChatGPT login.

Shell, web search, memories, plugins and skills are off and the sandbox is read-only, so the market's MCP tools are the
only tools it may call. Codex runs with its own CODEX_HOME, which holds only the login."""
import asyncio
import tempfile
import time
from pathlib import Path

from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox

from . import parse, retry

MODEL = dict(model='gpt-5.6-sol', effort='low')
OFF = ('shell_tool', 'memories', 'goals', 'plugins', 'skill_search', 'apps', 'browser_use', 'computer_use', 'tool_suggest', 'sleep_tool')
HOME = Path(tempfile.gettempdir()) / 'toolflation-codex'


def strict(schema):
    """Codex output schemas must list every property as required and forbid extras."""
    return {**schema, 'required': list(schema['properties']), 'additionalProperties': False}


async def turn(prompt, mcp, schema, timeout):
    (HOME / 'work').mkdir(parents=True, exist_ok=True)
    if not (HOME / 'auth.json').exists():
        (HOME / 'auth.json').symlink_to(Path.home() / '.codex/auth.json')
    config = {'features': {name: False for name in OFF}, 'web_search': 'disabled',
              'mcp_servers': {'market': {**mcp, 'default_tools_approval_mode': 'approve'}}}
    record = {'history': []}
    try:
        async with asyncio.timeout(timeout), AsyncCodex(CodexConfig(cwd=str(HOME / 'work'), env={'CODEX_HOME': str(HOME)})) as codex:
            thread = await codex.thread_start(model=MODEL['model'], cwd=str(HOME / 'work'), config=config, ephemeral=True,
                                              sandbox=Sandbox.read_only, approval_mode=ApprovalMode.deny_all)
            result = await thread.run(prompt, effort=MODEL['effort'], output_schema=strict(schema.model_json_schema()) if schema else None)
    except Exception as error:
        return {**record, 'error': f'{type(error).__name__}: {error}'}
    record.update(history=[item.model_dump(mode='json') for item in result.items], text=result.final_response or '',
                  stop_reason=result.status.value, usage=result.usage.total.model_dump(mode='json') if result.usage else None)
    if schema:
        record['structured'] = parse(record, schema)
    return record


async def chat(directory, prompt, mcp, schema=None, timeout=900):
    """A failed turn (rate limit, busy server) is retried on a fresh thread."""
    started = time.monotonic()
    record = await retry(lambda: turn(prompt, mcp, schema, timeout), attempts=3, wait=30)
    return {**record, 'seconds': time.monotonic() - started}
