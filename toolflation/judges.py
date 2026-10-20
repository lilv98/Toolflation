# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""The judges of what a description claims.

The claims judge, Gemini 3.8 Flash in Antigravity, reads which of the platform's fields a description says its tool
returns; the market calls it in every round. Claude Opus 5 then reads every distinct description once for a blanket
claim of completeness, which the claims judge ignores, and re-reads descriptions under the claims judge's instruction as
a check on the first judge.

python -m toolflation.judges blanket   # fills the blanket column of descriptions.jsonl
python -m toolflation.judges check     # writes judges.json
"""
import argparse
import asyncio
import json
import random
import re

from pydantic import BaseModel

from . import credentials, data, platforms
from .agents import session
from .measures import ROUNDS

CLAIMS = ('Below is the listing of a {noun} data tool and a list of {target} fields. Which of the fields does the listing claim '
          'the tool returns? Count a field only when the listing names it or an unmistakable synonym; generic phrases such as '
          '"all fields", "65+ fields", "full details" or "complete data" claim nothing. {note}Answer with the field ids only.\n\n')
BLANKET = ('Below is the listing of a {noun} data tool. Does the listing make a blanket claim of completeness, that is, say or imply '
           'that the tool returns all, nearly all or a large unnamed set of the available {target} data (for example "all fields", '
           '"65+ fields", "complete data", "every detail")? Naming many fields one by one is not a blanket claim. '
           'Reply with a JSON object {{"blanket": true}} or {{"blanket": false}} and nothing else.\n\nListing: ')
SAMPLE = 100  # descriptions per platform re-read by the second judge


class Claims(BaseModel):
    fields: list[str]


def claims_prompt(platform, fields, description):
    return CLAIMS.format(noun=platform.NOUN, target=platform.TARGET, note=platform.JUDGE_NOTE) \
        + json.dumps({'listing': description, 'fields': fields}, ensure_ascii=False)


async def claims(directory, platform, fields, description, attempts=5):
    """The ids of the fields a description claims. A failed call is retried with growing waits, then
    raised, since an empty answer would count as claiming nothing."""
    for attempt in range(attempts):
        response, _ = await session(directory, claims_prompt(platform, fields, description), 'gemini', schema=Claims)
        if not response.get('error') and response.get('structured') is not None:
            return sorted(set(response['structured']['fields']) & {f['id'] for f in fields})
        await asyncio.sleep(min(120, 15 * 2 ** attempt))
    raise RuntimeError(f'claims judge failed for {directory}: {response.get("error")}')


class Claude:
    """Claude Opus 5 called directly, with at most eight requests at a time; answers are one JSON object."""

    def __init__(self):
        from anthropic import AsyncAnthropicVertex
        self.client = AsyncAnthropicVertex(project_id=credentials.project(), region='global', max_retries=8)
        self.limit = asyncio.Semaphore(8)

    async def ask(self, prompt):
        async with self.limit:
            response = await self.client.messages.create(model='claude-opus-5', max_tokens=300, output_config={'effort': 'low'},
                                                         messages=[{'role': 'user', 'content': prompt}])
        return json.loads(re.search(r'\{.*\}', ''.join(b.text for b in response.content if b.type == 'text'), re.S).group(0))


async def blanket(claude, name):
    """Judge every description that has no blanket verdict yet, once per distinct text."""
    platform, path = platforms.load(name), data.DATA / name / 'descriptions.jsonl'
    rows = data.read(path)
    texts = sorted({r['description'] for r in rows if r['blanket'] is None})
    prompt = BLANKET.format(noun=platform.NOUN, target=platform.TARGET)
    verdicts = dict(zip(texts, await asyncio.gather(*(claude.ask(prompt + text) for text in texts))))
    data.write(path, [{**r, 'blanket': bool(verdicts[r['description']]['blanket'])} if r['blanket'] is None else r for r in rows])


async def check(claude, name):
    """The second judge on a random sample of distinct descriptions, and on every description of round zero and the
    final round of the seed-0 markets."""
    platform, fields = platforms.load(name), data.read(data.DATA / name / 'fields.json')
    ids = {f['id'] for f in fields}
    again = lambda text: claude.ask(claims_prompt(platform, fields, text) + '\n\nReply with a JSON object {"fields": [...]} and nothing else.')
    rows = [r for r in data.read(data.DATA / name / 'descriptions.jsonl') if (r['objective'], r['seed']) == ('neutral', 0) and r['round'] < ROUNDS]
    seen = {}
    for r in rows:
        seen.setdefault(r['description'], r['claims'])
    sample = random.Random(0).sample(sorted(seen), SAMPLE)
    ends = [r for r in rows if r['round'] in (0, ROUNDS - 1)]
    second = await asyncio.gather(*(again(text) for text in sample + [r['description'] for r in ends]))
    second = [sorted(set(s['fields']) & ids) for s in second]
    return {'distinct': len(seen), 'sample': [{'description': d, 'gemini': seen[d], 'claude': c} for d, c in zip(sample, second)],
            'ends': [{'buyer': r['buyer'], 'seller': r['seller'], 'round': r['round'], 'tool': r['tool'], 'gemini': r['claims'], 'claude': c}
                     for r, c in zip(ends, second[SAMPLE:])]}


async def main(command):
    claude = Claude()
    if command == 'blanket':
        for name in platforms.NAMES:
            await blanket(claude, name)
    else:
        data.write(data.DATA / 'judges.json', {name: await check(claude, name) for name in platforms.NAMES})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('blanket', 'check'))
    asyncio.run(main(parser.parse_args().command))
