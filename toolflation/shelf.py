# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""The shelf: the ten tools of a platform, chosen from the store by a fixed rule, and its questions.

python -m toolflation.shelf --platform amazon

Searches the store for the platform's name and keeps, in order of users in the last thirty days, the tools that are
public, maintained, billed per event or free, without a minimum charge per run and with a usable build, one per vendor
account, until ten are found. Writes shelf.json (every candidate with the reason it was kept or skipped), tools.json and
questions.json; targets.json and fields.json are written by hand. Mentions of fees in a vendor's description are then
removed by hand with the smallest change, so that round zero obeys the market's price rule ('original' keeps the text)."""
import argparse
import datetime as dt
import random

from . import data, platforms
from .apify import Apify

POOL, SIZE = 100, 10
MARKER = 'Actor description: '  # the store's MCP listing puts the vendor's description after this


def mentions(item, keywords):
    text = (item['title'] + ' ' + item['name']).lower().replace('-', ' ').replace('_', ' ')
    return any(keyword in text for keyword in keywords)


def skip_reason(actor, build):
    """Why a candidate may not enter the shelf, or None."""
    pricing = (actor.get('pricingInfos') or [{}])[-1]
    if not actor.get('isPublic') or actor.get('isDeprecated'):
        return 'not public or deprecated'
    if pricing.get('pricingModel') not in ('PAY_PER_EVENT', 'FREE'):
        return 'pricing model ' + str(pricing.get('pricingModel'))
    if pricing.get('minimalMaxTotalChargeUsd'):
        return 'minimum charge per run'
    if build.get('status') != 'SUCCEEDED' or not build.get('inputSchema'):
        return 'default build not usable'
    return None


def candidates(apify, platform):
    """Every searched tool in rank order with the reason it was skipped (None for the ten on the shelf)."""
    ranked = sorted(apify.store_search(platform.SEARCH, POOL), key=lambda i: (-i['stats']['totalUsers30Days'], -i['stats']['totalRuns'], i['id']))
    rows, accounts = [], set()
    for item in ranked:
        row = {'actor': item['username'] + '/' + item['name'], 'users_30d': item['stats']['totalUsers30Days'], 'runs': item['stats']['totalRuns']}
        if len(accounts) == SIZE:
            row['skip'] = 'shelf full'
        elif not mentions(item, platform.KEYWORDS):
            row['skip'] = 'name/title lacks ' + ' or '.join(platform.KEYWORDS)
        elif item['username'] in accounts:
            row['skip'] = 'account already on shelf'
        else:
            actor = apify.actor(row['actor'])
            tag = actor.get('defaultRunOptions', {}).get('build', 'latest')
            build = apify.build(actor['taggedBuilds'][tag]['buildId']) if tag in actor.get('taggedBuilds', {}) else {}
            row['skip'] = skip_reason(actor, build)
            if row['skip'] is None:
                accounts.add(item['username'])
        rows.append(row)
    assert len(accounts) == SIZE, f'only {len(accounts)} tools passed the filters'
    return rows


def aliases(n, seed=0):
    """Random names such as tool_kzqp, in no meaningful order, so that no name hints at what the tool does."""
    rng, names = random.Random(seed), set()
    while len(names) < n:
        names.add('tool_' + ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(4)))
    return sorted(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--platform', choices=platforms.NAMES, required=True)
    name = parser.parse_args().platform
    platform, apify, out = platforms.load(name), Apify(), data.DATA / name
    searched = dt.datetime.now(dt.timezone.utc).isoformat()
    rows = candidates(apify, platform)
    chosen = [r for r in rows if r['skip'] is None]
    listings = apify.mcp_tools([r['actor'] for r in chosen])
    tools = []
    for row, alias in zip(chosen, aliases(SIZE)):
        listing = next(t for t in listings if f'Actor "{row["actor"]}"' in t['description'])
        text = listing['description'].partition(MARKER)[2]
        tools.append({'alias': alias, **row, 'description': text, 'original': text, 'input_schema': listing['inputSchema']})
        del tools[-1]['skip']
    data.write(out / 'shelf.json', {'searched_at': searched, 'search': platform.SEARCH, 'pool': POOL,
                                    'rule': 'rank by users_30d, runs, id; keep public, non-deprecated, pay-per-event or free, no minimum charge, '
                                            f'usable default build, {" or ".join(platform.KEYWORDS)} in name/title, one actor per account',
                                    'candidates': rows})
    data.write(out / 'tools.json', tools)
    data.write(out / 'questions.json', platforms.questions(platform, data.read(out / 'targets.json'), data.read(out / 'fields.json')))


if __name__ == '__main__':
    main()
