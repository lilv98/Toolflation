# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""Gemini 3.8 Flash in Antigravity, through the Antigravity SDK on Vertex AI."""
import asyncio
import copy
import json
import os
import time

from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
from google.antigravity.connections.local.event_processor import LocalConnectionStep
from google.antigravity.hooks import policy
from google.antigravity.models import GeminiModelOptions, ModelTarget, ThinkingLevel, VertexEndpoint
from google.antigravity.types import BudgetConfig, McpStdioServer, ModelAPIRetryConfig, RetryConfig
from pydantic import BaseModel

from .. import credentials

MODEL = dict(model='gemini-3.8-flash', location=os.getenv('GOOGLE_CLOUD_LOCATION', 'global'))
_from_dict = LocalConnectionStep.from_dict


def _normalised(cls, step):
    """Decode MCP arguments that the history stores as doubly encoded JSON."""
    step = copy.deepcopy(step)
    for value in (step.get('mcp_tool'), step.get('custom_tool', {}).get('tool_call')):
        if isinstance(value, dict) and value.get('arguments_json'):
            try:
                decoded = json.loads(value['arguments_json'])
                if isinstance(decoded, str):
                    value['arguments_json'] = json.dumps(json.loads(decoded))
            except (json.JSONDecodeError, TypeError):
                pass
    return _from_dict(step)


LocalConnectionStep.from_dict = classmethod(_normalised)


def config(directory, **kwargs):
    project = credentials.project()
    return LocalAgentConfig(
        vertex=True, project=project, location=MODEL['location'],
        model=ModelTarget(name=MODEL['model'], endpoint=VertexEndpoint(project=project, location=MODEL['location'],
                                                                       options=GeminiModelOptions(thinking_level=ThinkingLevel.LOW))),
        capabilities=CapabilitiesConfig(enabled_tools=[], enable_subagents=False), policies=[policy.allow_all()],
        retry_config=RetryConfig(api_retry=ModelAPIRetryConfig(max_retries=3, initial_sleep_duration_ms=1000)),
        budget_config=BudgetConfig(max_model_calls=12, max_tool_calls=12, max_output_tokens=18000),
        workspaces=[str(directory)], app_data_dir=str(directory / 'app'), save_dir=str(directory / 'session'), **kwargs)


async def chat(directory, prompt, mcp=None, schema=None, timeout=900):
    """The claims judge also runs here, without a market (mcp=None)."""
    kwargs = {}
    if mcp:
        kwargs['mcp_servers'] = [McpStdioServer(name='market', command=mcp['command'], args=mcp['args'], env=mcp['env'], timeout_seconds=360)]
    if schema:
        kwargs['response_schema'] = schema
    record, started = {'history': []}, time.monotonic()
    try:
        async with asyncio.timeout(timeout), Agent(config(directory, **kwargs)) as agent:
            try:
                response = await agent.chat(prompt)
                record['text'] = await response.text()
                structured = await response.structured_output()
                record['structured'] = structured.model_dump(mode='json') if isinstance(structured, BaseModel) else structured
                record['stop_reason'] = response.stop_reason.value
            finally:
                record['history'] = [s.model_dump(mode='json') for s in agent.conversation.history]
    except Exception as error:
        record['error'] = f'{type(error).__name__}: {error}'
    return {**record, 'seconds': time.monotonic() - started}
