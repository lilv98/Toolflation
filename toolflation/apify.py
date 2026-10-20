# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""The Apify API: store search, actor metadata, the official MCP listings of actors, and paid runs."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import credentials

API = 'https://api.apify.com/v2/'
MCP = 'https://mcp.apify.com/'


def sanitize(value, private):
    """Null out personal-data fields (key fragments in `private`) before anything is logged or shown to a model."""
    if isinstance(value, list):
        return [sanitize(item, private) for item in value]
    if isinstance(value, dict):
        return {key: None if any(p in key.lower() for p in private) else sanitize(item, private)
                for key, item in value.items()}
    return value


class Apify:
    def __init__(self, token=None):
        self.token = token or credentials.key('apify')['api_key']

    def request(self, path, body=None, retries=3, raw=False, **query):
        """GET when body is None, else POST. Only reads are retried: a lost POST may have started a paid run."""
        url = API + path + ('?' + urllib.parse.urlencode(query) if query else '')
        request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        attempts = retries if body is None else 1
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = json.load(response)
                    return payload if raw else payload['data']
            except urllib.error.HTTPError as error:
                detail = error.read().decode(errors='replace')[:500]
                if attempt == attempts - 1 or error.code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f'Apify HTTP {error.code}: {detail}') from None
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt == attempts - 1:
                    raise
            time.sleep(attempt + 1)

    def store_search(self, search, limit=100):
        return self.request('store', search=search, limit=limit, offset=0)['items']

    def actor(self, actor_id):
        return self.request('acts/' + actor_id.replace('/', '~'))

    def build(self, build_id):
        return self.request('actor-builds/' + build_id)

    def mcp_tools(self, actor_ids):
        """Official MCP tools/list entries (name, description, inputSchema) for the given actors."""
        url = MCP + '?' + urllib.parse.urlencode({'tools': ','.join(actor_ids)})
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json',
                   'Accept': 'application/json, text/event-stream'}

        def rpc(request_id, method, params):
            request = urllib.request.Request(url, headers=headers, data=json.dumps(
                {'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}).encode())
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read().decode()
                if response.headers.get('Mcp-Session-Id'):
                    headers['Mcp-Session-Id'] = response.headers['Mcp-Session-Id']
            messages = [json.loads(line[6:]) for line in body.splitlines() if line.startswith('data: ')]
            message = next(m for m in (messages or [json.loads(body)]) if m.get('id') == request_id)
            if 'error' in message:
                raise RuntimeError(message['error'])
            return message['result']

        rpc(1, 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                              'clientInfo': {'name': 'toolflation', 'version': '2'}})
        result = rpc(2, 'tools/list', {})
        tools, request_id = result['tools'], 3
        while result.get('nextCursor'):
            result = rpc(request_id, 'tools/list', {'cursor': result['nextCursor']})
            tools.extend(result['tools'])
            request_id += 1
        return tools

    def run(self, actor_id, actor_input, max_usd, private=(), timeout=240):
        """Start one paid run, wait for it, return its items with `private` keys nulled. Never retries the start."""
        record = {'actor': actor_id, 'input': actor_input, 'run_id': None, 'status': None,
                  'items': [], 'usd': None, 'error': None}
        try:
            run = self.request(f'acts/{actor_id.replace("/", "~")}/runs', body=actor_input,
                               timeout=timeout, maxTotalChargeUsd=max_usd)
            record['run_id'] = run['id']
            deadline = time.monotonic() + timeout + 60
            while run['status'] in ('READY', 'RUNNING', 'TIMING-OUT', 'ABORTING'):
                if time.monotonic() > deadline:
                    self.request(f'actor-runs/{run["id"]}/abort', body={})
                    raise TimeoutError('run wait exceeded; abort requested')
                run = self.request(f'actor-runs/{run["id"]}', waitForFinish=30)
            record['status'] = run['status']
            record['usd'] = run.get('usageTotalUsd')
            if run['status'] == 'SUCCEEDED':
                record['items'] = sanitize(self.dataset(run['defaultDatasetId']), private)
            else:
                record['error'] = 'run ended with ' + run['status']
        except Exception as error:
            record['error'] = f'{type(error).__name__}: {error}'
        return record

    def dataset(self, dataset_id):
        items = []
        while True:
            page = self.request(f'datasets/{dataset_id}/items', raw=True, format='json', clean='true',
                                offset=len(items), limit=1000)
            items.extend(page)
            if len(page) < 1000:
                return items
