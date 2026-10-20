# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""The capability matrix: every tool on the shelf runs once for every target, and fixed rules grade every field.

python -m toolflation.matrix --platform amazon

A run that fails is repeated once. The raw runs go to raw/<platform>/runs.jsonl and the verdicts to matrix.jsonl. The
tools are then numbered by the questions they answer (A0 answers most), and each gets the output record its seller is
shown: its first run that found the target, else its first run that returned anything, cut down to its shape."""
import argparse
from concurrent.futures import ThreadPoolExecutor

from . import data, platforms
from .apify import Apify
from .grading import classify, service_error

MAX_USD = 0.05  # charge cap per run, unless the platform sets a higher one for a tool that charges a flat fee


def trimmed(value, depth=0):
    """A record cut down to its shape: every key, the first two items of each list, strings up to 200 characters."""
    if depth > 6:
        return '...'
    if isinstance(value, dict):
        return {k: trimmed(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [trimmed(v, depth + 1) for v in value[:2]] + (['...'] if len(value) > 2 else [])
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + '...'
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--platform', choices=platforms.NAMES, required=True)
    parser.add_argument('--workers', type=int, default=5)
    args = parser.parse_args()
    name = args.platform
    platform, apify, out = platforms.load(name), Apify(), data.DATA / name
    tools, targets, fields = data.read(out / 'tools.json'), data.read(out / 'targets.json'), [f['id'] for f in data.read(out / 'fields.json')]
    cells = [(tool['actor'], target) for tool in tools for target in targets]
    run = lambda cell: {'target': cell[1]['id'], **apify.run(cell[0], platform.BUILDERS[cell[0]](cell[1]), platform.CAP.get(cell[0], MAX_USD),
                                                             private=platform.PRIVATE)}
    failed = lambda r: bool(r['error'] or service_error(r['items']))
    with ThreadPoolExecutor(args.workers) as pool:
        runs = list(pool.map(run, cells))
        again = [i for i, r in enumerate(runs) if failed(r)]
        for i, r in zip(again, pool.map(lambda i: run(cells[i]), again)):
            runs[i] = {**r, 'retried': True}
    data.write(data.RAW / name / 'runs.jsonl', runs)
    verdicts = {(actor, target['id']): classify(platform, r, target, fields) for (actor, target), r in zip(cells, runs)}
    answers = {t['actor']: sum(v == 'delivered' for (actor, _), cell in verdicts.items() if actor == t['actor'] for v in cell.values()) for t in tools}
    code = {actor: f'{name[0].upper()}{rank}' for rank, actor in enumerate(sorted(answers, key=lambda a: (-answers[a], a)))}

    def sample(actor):
        mine = [r for (a, _), r in zip(cells, runs) if a == actor and r['items'] and not r['error']]
        found = [r for r in mine if set(verdicts[actor, r['target']].values()) <= {'delivered', 'missing'}]
        return trimmed((found or mine or [{'items': [None]}])[0]['items'][0])
    data.write(out / 'tools.json', [{'tool': code[t['actor']], **{k: v for k, v in t.items() if k != 'tool'}, 'sample_output': sample(t['actor'])}
                                    for t in tools])
    data.write(out / 'matrix.jsonl', [{'tool': code[actor], 'target': target, 'field': f, 'verdict': cell[f]}
                                      for (actor, target), cell in sorted(verdicts.items(), key=lambda kv: int(code[kv[0][0]][1:])) for f in fields])


if __name__ == '__main__':
    main()
