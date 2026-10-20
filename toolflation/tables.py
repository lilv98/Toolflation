# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""The tables of the paper's appendix, as LaTeX.

python -m toolflation.tables out/   # markets.tex, history.tex, rewrites.tex, judges.tex, blankets.tex, objectives.tex

The cost table needs the token counts of every agent session, which the dataset does not include."""
import statistics
import sys
from pathlib import Path

from . import data
from .agents import HARNESSES, MODELS, name
from .measures import BUYERS, ROUNDS, SELLERS, Shelf, fmt

PLATFORMS = {'amazon': 'Amazon', 'instagram': 'Instagram'}
SHORT = {'claude': 'Claude', 'codex': 'GPT-5.6 Sol', 'grok': 'Grok', 'deepseek': 'DeepSeek', 'gemini': 'Gemini'}
ESCAPES = {'&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\^{}'}


def escape(text):
    return ''.join(ESCAPES.get(c, c) for c in text)


def tabular(columns, head, rows):
    return '\n'.join([rf'\begin{{tabular}}{{{columns}}}', r'\toprule', *head, *rows, r'\bottomrule', r'\end{tabular}']) + '\n'


def markets(shelves):
    """One row per market and seed: success, onset, volatility, what sellers wrote and where the choices went."""
    head = [r'Platform & Buyer & Seller & Rounds & \multicolumn{2}{c}{Success (\%)} & Onset & SD & Claimed & Overcl. & Unsupp. & Simil. & First & Top & Weak \\',
            r' & & & & $r_0$ & last 5 & & last 10 & last 5 & last 5 & last 5 & last 5 & last 5 & last 5 & total \\']
    rows = []
    for shelf in shelves:
        rows.append(r'\midrule')
        runs = shelf.runs()
        for buyer in BUYERS:
            for seller in SELLERS:
                for k, rounds in enumerate(runs[buyer, seller]):
                    success = [r['success'] for r in rounds]
                    onset = next((i for i, s in enumerate(success) if s < 0.85 * success[0]), None)
                    final = lambda key: statistics.mean(r[key] for r in rounds[-5:])
                    weak = sum(r['selections'][t] for r in rounds for t in shelf.weak)
                    rows.append(' & '.join([
                        PLATFORMS[shelf.name] if (buyer, seller, k) == (BUYERS[0], SELLERS[0], 0) else '',
                        HARNESSES[buyer] if (seller, k) == (SELLERS[0], 0) else '',
                        SHORT[seller] + (f', seed {k}' if k else ''), str(len(rounds)), fmt(success[0]), fmt(statistics.mean(success[-5:])),
                        '---' if onset is None else str(onset), fmt(statistics.stdev(success[-10:]), 1), fmt(final('claims'), 1),
                        fmt(final('overclaims'), 1), fmt(final('unsupported'), 1), fmt(final('similarity'), 2), f'{fmt(final("first"))}\\%',
                        f'{fmt(final("best"))}\\%', f'{weak:,}']) + r' \\')
    return tabular('lllrrrrrrrrrrrr', head, rows)


def history(amazon, tool='A9'):
    """The seller-contact database across the rounds of the Amazon markets with Claude Code as the buyer."""
    def row(label, seller, round_id):
        market = ('claude', seller, 'neutral', 0)
        picks = amazon.rounds[market][round_id]['selections'][tool]
        return f'{label} & {picks} & {escape(amazon.description(market, round_id, tool)["description"])} \\\\'
    rows = [rf'\multicolumn{{3}}{{l}}{{\textit{{{name("gemini")}}}}} \\']
    rows += [row(r, 'gemini', r) for r in (0, 1, 2, 4, 6, 8, 12, ROUNDS - 1)]
    rows += [r'\midrule', rf'\multicolumn{{3}}{{l}}{{\textit{{Round {ROUNDS - 1} under the other seller models}}}} \\']
    rows += [row(MODELS[seller], seller, ROUNDS - 1) for seller in SELLERS if seller != 'gemini']
    return tabular(r'p{0.08\linewidth}rp{0.77\linewidth}', [r'Round & Picks & Description \\', r'\midrule'], rows)


def rewrites(shelves):
    """Per seller model, over the seed-0 markets of both platforms: how often sellers rewrote, how often the rules refused
    a submission, and how long the descriptions of the last round are."""
    rows = []
    for seller in SELLERS:
        turns = [r for s in shelves for r in s.tables['rewrites'] if (r['seller'], r['objective'], r['seed']) == (seller, 'neutral', 0)]
        refused = lambda word: sum(word in str(sub['rejected']) for r in turns for sub in r['submissions'])
        lengths = [len(r['description']) for s in shelves for r in s.tables['descriptions']
                   if (r['seller'], r['objective'], r['seed'], r['round']) == (seller, 'neutral', 0, ROUNDS - 1)]
        rows.append(f'{name(seller)} & {len(turns):,} & {fmt(100 * sum(r["before"] != r["after"] for r in turns) / len(turns))}\\% & '
                    f'{refused("longer"):,} & {refused("price")} & {fmt(statistics.mean(lengths))} \\\\')
    head = [r'Seller agent & Turns & Rewrote & Refused, length & Refused, price & Final length \\', r'\midrule']
    return tabular('lrrrrr', head, rows)


def judges(shelves):
    """The second claims judge: per-field agreement and Cohen's kappa on a random sample, and unsupported claims in round
    zero and the final round under both judges."""
    check, n = data.read(data.DATA / 'judges.json'), len(SELLERS) + 1
    head = [rf' & \multicolumn{{2}}{{c}}{{Random sample}} & \multicolumn{{{n}}}{{c}}{{Unsupported claims, Gemini / Claude judge}} \\',
            rf'\cmidrule(lr){{2-3}}\cmidrule(lr){{4-{3 + n}}}',
            r"Platform & Agreement & Cohen's kappa & Originals & " + ' & '.join(SHORT[m] for m in SELLERS) + r' \\', r'\midrule']
    rows = []
    for shelf in shelves:
        c = check[shelf.name]
        pairs = [(f in r['gemini'], f in r['claude']) for r in c['sample'] for f in shelf.fields]  # one decision per description and field
        agreement = statistics.mean(g == k for g, k in pairs)
        pg, pc = statistics.mean(g for g, _ in pairs), statistics.mean(k for _, k in pairs)
        chance = pg * pc + (1 - pg) * (1 - pc)
        kappa = (agreement - chance) / (1 - chance)
        unsupported = lambda group, judge: statistics.mean(len(set(r[judge]) - shelf.evidence[r['tool']]) for r in group)
        groups = [[r for r in c['ends'] if r['round'] == 0]] + [[r for r in c['ends'] if r['round'] and r['seller'] == m] for m in SELLERS]
        cells = [f'{fmt(unsupported(g, "gemini"), 1)} / {fmt(unsupported(g, "claude"), 1)}' for g in groups]
        rows.append(f'{PLATFORMS[shelf.name]} & {fmt(100 * agreement)}\\% & {fmt(kappa, 2)} & ' + ' & '.join(cells) + r' \\')
    return tabular('lcc' + 'c' * n, head, rows)


def blankets(shelves):
    """Blanket claims of completeness: the share of descriptions that make one, and the share made by a tool whose own
    sample record shows fewer than half of the fields, in round zero and over the last five rounds of each seller model."""
    head = [r'Platform & Originals & ' + ' & '.join(SHORT[m] for m in SELLERS) + r' \\', r'\midrule']
    rows = []
    for shelf in shelves:
        runs = shelf.runs()
        share = lambda rounds: [100 * statistics.mean(r[k] for r in rounds) for k in ('blanket', 'blanket_sparse')]
        start = share(next(iter(runs.values()))[0][:1])
        ends = [[statistics.mean(v) for v in zip(*[share(rs[-5:]) for (_, seller), seeds in runs.items() if seller == m for rs in seeds])]
                for m in SELLERS]
        rows.append(f'{PLATFORMS[shelf.name]} & ' + ' & '.join(f'{fmt(a)} / {fmt(b)}' for a, b in [start] + ends) + r' \\')
    return tabular('l' + 'c' * (len(SELLERS) + 1), head, rows)


def objectives(amazon):
    """The seller objectives on Amazon with Claude Code as the buyer, over rounds 5 to 9; neutral is the mean over the
    three seeds of the main markets."""
    head = [r'Seller agent & Objective & Success (\%) & $\ell_{\mathrm{weak}}$ (\%) & $u$ & $\sigma$ & $f$ (\%) \\', r'\midrule']
    rows = []
    for seller in ('gemini', 'codex'):
        for objective in ('neutral', 'honest', 'pressure'):
            rounds = [r for (b, s, o, _), rs in amazon.rounds.items() if (b, s, o) == ('claude', seller, objective) for r in rs[5:10]]
            mean = lambda key: statistics.mean(r[key] for r in rounds)
            rows.append(' & '.join([name(seller) if objective == 'neutral' else '', objective, fmt(mean('success')), fmt(mean('lost_weak'), 1),
                                    fmt(mean('unsupported'), 1), fmt(mean('similarity'), 2), fmt(mean('first'))]) + r' \\')
    return tabular('llrrrrr', head, rows)


def main(directory):
    directory.mkdir(parents=True, exist_ok=True)
    shelves = [Shelf(p) for p in PLATFORMS]
    tables = {'markets': markets(shelves), 'history': history(shelves[0]), 'rewrites': rewrites(shelves), 'judges': judges(shelves),
              'blankets': blankets(shelves), 'objectives': objectives(shelves[0])}
    for table, text in tables.items():
        (directory / f'{table}.tex').write_text(text)


if __name__ == '__main__':
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else data.ROOT / 'out')
