# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""Claude Opus 5 in Claude Code, through the Claude Agent SDK on Vertex AI.

Claude Code keeps its own system prompt; its built-in tools are off, user and project settings are not loaded, and the
market's MCP tools are the only tools it may call."""
import asyncio
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, UserMessage, query

from .. import credentials
from . import parse

MODEL = dict(model='claude-opus-5', region='global', effort='low')
MAX_TURNS = 12
HOME = Path(tempfile.gettempdir()) / 'toolflation-claude'


async def chat(directory, prompt, mcp, schema=None, timeout=900):
    (HOME / 'work').mkdir(parents=True, exist_ok=True)
    env = {'CLAUDE_CODE_USE_VERTEX': '1', 'ANTHROPIC_VERTEX_PROJECT_ID': credentials.project(), 'CLOUD_ML_REGION': MODEL['region'],
           'CLAUDE_CONFIG_DIR': str(HOME / 'config'), 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1', 'DISABLE_AUTOUPDATER': '1'}
    options = ClaudeAgentOptions(
        model=MODEL['model'], effort=MODEL['effort'], system_prompt={'type': 'preset', 'preset': 'claude_code'}, tools=[],
        mcp_servers={'market': {'type': 'stdio', **mcp}}, strict_mcp_config=True, allowed_tools=['mcp__market'],
        permission_mode='dontAsk', setting_sources=[], max_turns=MAX_TURNS, cwd=str(HOME / 'work'), env=env)
    record, history, started = {}, [], time.monotonic()
    try:
        async with asyncio.timeout(timeout):
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, (AssistantMessage, UserMessage)):
                    history.append({'role': type(message).__name__, **asdict(message)})
                elif isinstance(message, ResultMessage):
                    record.update(text=message.result or '', stop_reason=message.stop_reason or message.subtype, usage=message.usage)
                    if message.is_error:
                        record['error'] = message.subtype
        if schema:
            record['structured'] = parse(record, schema)
    except Exception as error:
        record['error'] = f'{type(error).__name__}: {error}'
    return {**record, 'history': history, 'seconds': time.monotonic() - started}
