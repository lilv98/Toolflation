# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""The measures of the paper, computed from the released tables.

Per round of a market, on the buyer side: task success s, the questions lost to weak tools and to capable tools, the
first-listed share f and the share of the most capable tool m, all in percent of the questions. On the seller side, per
description: the claimed fields κ, the unsupported claims u, the overclaimed fields o, the similarity σ of the ten
descriptions, and the share of descriptions with a blanket claim of completeness."""
import itertools
import re
import statistics
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal

from . import data, platforms

ROUNDS = 20  # rounds of every main market
LAST = 5  # a market's final value is its mean over its last five rounds
WEAK = 0.1  # a weak tool answers fewer than this share of the questions
BUYERS = ('claude', 'codex')
SELLERS = ('claude', 'codex', 'grok', 'deepseek', 'gemini')


def fmt(x, digits=0, sep=''):
    """Round half-up, the one rule for every number in the paper; sep=',' adds thousands separators."""
    value = Decimal(repr(round(float(x), 9))).quantize(Decimal(1).scaleb(-digits), ROUND_HALF_UP)
    return format(value, f'{sep}f')


def last(values):
    return statistics.mean(values[-LAST:])


def similarity(descriptions):
    """Mean Jaccard overlap between the word sets of every pair of descriptions."""
    words = [set(re.findall(r'[a-z0-9]+', d.lower())) for d in descriptions]
    return statistics.mean(len(a & b) / len(a | b) for a, b in itertools.combinations(words, 2))


class Shelf:
    """One platform: its tools, capability matrix and questions, and the measures of every round of every market."""

    def __init__(self, name, directory=data.DATA):
        tables = data.load(name, directory)
        self.name, self.platform, self.tables = name, platforms.load(name), tables
        self.fields = [f['id'] for f in tables['fields']]
        self.targets = [t['id'] for t in tables['targets']]
        self.questions = {q['id']: q for q in tables['questions']}
        self.tools = sorted(tables['tools'], key=lambda t: int(t['tool'][1:]))
        self.codes = [t['tool'] for t in self.tools]  # most capable first
        self.verdict = {(r['tool'], r['target'], r['field']): r['verdict'] for r in tables['matrix']}
        self.answers = Counter(tool for (tool, _, _), v in self.verdict.items() if v == 'delivered')
        self.weak = {t for t in self.codes if self.answers[t] < WEAK * len(self.questions)}
        self.best = self.codes[0]
        self.delivers = {t: {f: statistics.mean(self.verdict[t, x, f] == 'delivered' for x in self.targets) for f in self.fields}
                         for t in self.codes}  # share of targets for which a tool returns a field
        self.evidence = {t['tool']: platforms.evidence(self.platform, t['sample_output'], self.fields) for t in self.tools}
        descriptions, choices = defaultdict(list), defaultdict(list)
        for row in tables['descriptions']:
            descriptions[data.market(row)].append(row)
        for row in tables['choices']:
            choices[data.market(row)].append(row)
        self.rounds = {m: [self.measure(rows, [c for c in choices[m] if c['round'] == r])
                           for r, rows in itertools.groupby(sorted(ds, key=lambda d: d['round']), key=lambda d: d['round'])]
                       for m, ds in descriptions.items()}

    def answered(self, tool, question):
        q = self.questions[question]
        return self.verdict.get((tool, q['target'], q['field'])) == 'delivered'

    def baselines(self):
        """(ρ, β) in percent: the success of a random choice and of always choosing a tool that answers."""
        able = [[self.answered(t, q) for t in self.codes] for q in self.questions]
        return 100 * statistics.mean(sum(a) / len(a) for a in able), 100 * statistics.mean(any(a) for a in able)

    def measure(self, descriptions, choices):
        n, d = len(choices), list(descriptions)
        lost = [c['choice'] in self.weak for c in choices
                if not self.answered(c['choice'], c['question']) and any(self.answered(t, c['question']) for t in self.codes)]
        claims = [(r['tool'], f) for r in d for f in r['claims']]
        sparse = {t for t, shown in self.evidence.items() if len(shown) < len(self.fields) / 2}
        return {'round': d[0]['round'], 'questions': n, 'selections': Counter(c['choice'] for c in choices if c['choice']),
                'success': 100 * sum(self.answered(c['choice'], c['question']) for c in choices) / n,
                'lost_weak': 100 * sum(lost) / n, 'lost_capable': 100 * (len(lost) - sum(lost)) / n,
                'first': 100 * sum(c['choice'] == c['listing'][0] for c in choices) / n,
                'best': 100 * sum(c['choice'] == self.best for c in choices) / n,
                'distinct': len({r['description'] for r in d}), 'similarity': similarity([r['description'] for r in d]),
                'claims': len(claims) / len(d), 'overclaims': sum(self.delivers[t][f] < 0.5 for t, f in claims) / len(d),
                'unsupported': sum(f not in self.evidence[t] for t, f in claims) / len(d),
                'blanket': statistics.mean(r['blanket'] for r in d),
                'blanket_sparse': statistics.mean(r['blanket'] and r['tool'] in sparse for r in d)}

    def runs(self, objective='neutral'):
        """(buyer, seller) -> the rounds of each of its seeds, cut to the reported rounds."""
        out = defaultdict(list)
        for (buyer, seller, o, seed), rounds in sorted(self.rounds.items()):
            if o == objective:
                out[buyer, seller].append(rounds[:ROUNDS])
        return dict(out)

    def series(self, key):
        """(buyer, seller) -> one value per round, the mean over the market's seeds."""
        return {m: [statistics.mean(seed[i][key] for seed in seeds) for i in range(len(seeds[0]))] for m, seeds in self.runs().items()}

    def description(self, market, round_id, tool):
        return next(r for r in self.tables['descriptions'] if data.market(r) == market and r['round'] == round_id and r['tool'] == tool)
