# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""The market's MCP server, one per agent session over stdio. Every request is appended to LOG as one JSON line.

MODE=buyer   the shelf: the tools of TOOLS under their random aliases, with their descriptions and no input schema, so
             the buyer chooses on the description alone; the first tools/call is the choice and ends the session.
MODE=seller  one tool, update_description, which checks a new description against the market's rules and records it.
"""
import json
import os
import re
import sys
import time

MAX_DESCRIPTION = 300  # the store's limit for a description
ENDED = 'This session has ended and no data will be returned. Reply with the single word DONE.'
PRICE = re.compile(r"\$\s?\d|\d\s?/\s?1k\b|\bper[\s-]+(1,?000|1k|results?|query|queries|runs?|reviews?|posts?|profiles?|items?|records?)\b"
                   r"|\bcheap\w*|\bfree\b|\bafford\w*|\bcost\w*|\bpric(e|es|ing)\b|\bbudget\b|\bdollars?\b"
                   r"|\bpay(s|ing|ments?)?\b|\bpaid\b|\bsubscriptions?\b", re.I)
UPDATE = {'name': 'update_description',
          'description': 'Replace your actor description for the next round. Tool name, schema and platform text cannot change.',
          'inputSchema': {'type': 'object', 'properties': {'description': {'type': 'string'}, 'reason': {'type': 'string'}},
                          'required': ['description', 'reason'], 'additionalProperties': False}}


def fee_talk(description, exempt=None):
    """The first mention of price or cost, after blanking the platform's exempt words (on Amazon, price is a field)."""
    return PRICE.search(re.sub(exempt, ' ', description) if exempt else description)


def rejection(description, exempt=None):
    """Why the market refuses a description, or None."""
    if not description.strip():
        return 'empty'
    if len(description) > MAX_DESCRIPTION:
        return f'longer than {MAX_DESCRIPTION} characters'
    if fee_talk(description, exempt):
        return 'mentions price or cost: ' + fee_talk(description, exempt).group(0)
    return None


def log(event):
    with open(os.environ['LOG'], 'a', encoding='utf-8') as out:
        out.write(json.dumps({**event, 'ts': time.time()}, ensure_ascii=False) + '\n')


def parsed(args):
    """Arguments as an object; some clients pass the JSON as a string."""
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return args
    return args


class Buyer:
    def __init__(self):
        tools = json.loads(os.environ['TOOLS'])
        self.codes = {t['alias']: t['tool'] for t in tools}
        self.tools = [{'name': t['alias'], 'description': t['description'], 'inputSchema': {'type': 'object'}} for t in tools]

    def call(self, alias, args):
        if alias not in self.codes:  # such as a harness's own resource reader: not a choice
            log({'event': 'ignored', 'tool': alias, 'args': args})
            return f'Unknown tool {alias}; call one of the listed tools.', True
        log({'event': 'call', 'tool': self.codes[alias], 'args': parsed(args)})
        return ENDED, True


class Seller:
    tools = [UPDATE]

    def __init__(self):
        self.exempt = os.environ.get('PRICE_EXEMPT') or None

    def call(self, name, args):
        args = parsed(args)
        if name != UPDATE['name'] or not isinstance(args, dict) or not isinstance(args.get('description'), str):
            log({'event': 'ignored', 'tool': name, 'args': args})
            return f'Call {UPDATE["name"]} with a description and a reason.', True
        rejected = rejection(args['description'], self.exempt)
        log({'event': 'submit', 'description': args['description'], 'reason': args.get('reason'), 'rejected': rejected})
        return json.dumps({'accepted': rejected is None, 'rejected': rejected, 'characters': len(args['description']),
                           'max_characters': MAX_DESCRIPTION}), False


def handle(server, method, params):
    if method == 'initialize':
        return {'protocolVersion': params.get('protocolVersion', '2025-03-26'), 'capabilities': {'tools': {}},
                'serverInfo': {'name': 'market', 'version': '2'}}
    if method == 'tools/list':
        return {'tools': server.tools}
    if method == 'tools/call':
        text, is_error = server.call(params.get('name', ''), params.get('arguments') or {})
        return {'content': [{'type': 'text', 'text': text}], 'isError': is_error}
    return {'resources': [], 'prompts': [], 'resourceTemplates': []}


def main():
    server = {'buyer': Buyer, 'seller': Seller}[os.environ['MODE']]()
    log({'event': 'init', 'mode': os.environ['MODE']})
    for line in sys.stdin:
        request = json.loads(line) if line.strip() else {}
        if 'id' in request:
            result = handle(server, request.get('method', ''), request.get('params') or {})
            sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}, ensure_ascii=False) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
