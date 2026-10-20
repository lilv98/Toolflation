# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""The agents: each model runs in its vendor's own harness, one module per vendor.

Every backend has chat(directory, prompt, mcp, schema=None), one fresh session that reaches the market only through the
MCP server described by mcp, and returns {'text', 'structured', 'stop_reason', 'usage', 'history'} or {'error', ...}.
Sessions start in an empty directory outside the repository, so no project instructions or user settings reach the
model. A backend is imported when it is first used, so the analysis needs none of the harnesses."""
import asyncio
import importlib
import sys

from .. import data

MODELS = {'claude': 'Claude Opus 5', 'codex': 'GPT-5.6 Sol', 'grok': 'Grok 4.6', 'deepseek': 'DeepSeek V4.1 Flash',
          'gemini': 'Gemini 3.8 Flash'}
HARNESSES = {'claude': 'Claude Code', 'codex': 'Codex', 'grok': 'Grok Build', 'deepseek': 'DeepSeek Harness', 'gemini': 'Antigravity'}


def name(agent):
    """A seller agent as the paper writes it, model and harness: Gemini 3.8 Flash (Antigravity)."""
    return f'{MODELS[agent]} ({HARNESSES[agent]})'


def backend(agent):
    return importlib.import_module(f'{__name__}.{agent}').chat


def parse(record, schema):
    """The final text as an instance of schema, for harnesses without structured output; None when it is not that JSON."""
    try:
        return schema.model_validate_json(record.get('text', '')).model_dump(mode='json')
    except ValueError:
        return None


async def retry(run, attempts, wait=0):
    """Run a session until it ends without error, at most attempts times, waiting wait × attempt seconds in between."""
    for attempt in range(1, attempts + 1):
        record = await run()
        if not record.get('error') or attempt == attempts:
            return {**record, 'attempts': attempt}
        await asyncio.sleep(wait * attempt)


def server(mode, directory, **env):
    """The market's MCP server for one session, logging next to it."""
    return {'command': sys.executable, 'args': ['-m', 'toolflation.server'],
            'env': {'MODE': mode, 'LOG': str(directory / 'mcp.jsonl'), 'PYTHONPATH': str(data.ROOT), **env}}


async def session(directory, prompt, agent, mcp=None, schema=None):
    """One fresh session; its prompt, history, response and MCP log land in directory. Returns the response and the log."""
    directory.mkdir(parents=True, exist_ok=True)
    data.write(directory / 'prompt.json', {'prompt': prompt})
    record = await backend(agent)(directory, prompt, mcp, schema)
    data.write(directory / 'history.json', record.pop('history', []))
    data.write(directory / 'response.json', record)
    return record, data.read(directory / 'mcp.jsonl')
