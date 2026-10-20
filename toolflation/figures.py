# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""The figures of the paper, as PDF.

python -m toolflation.figures out/

overview.pdf, capability-amazon.pdf, capability-instagram.pdf, dynamics.pdf, metrics.pdf, raw.pdf, shares.pdf and
outcomes.pdf. Curves average the markets of a seller model, with a band over their range, and after round zero are
three-round moving averages."""
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.transforms import blended_transform_factory

from . import data
from .agents import HARNESSES, MODELS, name
from .measures import BUYERS, ROUNDS, SELLERS, Shelf, fmt
from .tables import PLATFORMS

COLOURS = {'claude': '#2a78d6', 'codex': '#1baf7a', 'grok': '#8a5cc2', 'deepseek': '#c9a227', 'gemini': '#eb6834'}
INK, MUTED, RULE, PANEL = '#0b0b0b', '#52514e', '#d9d8d2', '#f4f3ef'
SUPPORTED, UNSUPPORTED = '#3d3d3a', '#d1452f'
BLUES = LinearSegmentedColormap.from_list('blues', ['#ffffff', '#cde2fb', '#86b6ef', '#3987e5', '#1c5cab', '#0d366b'])
OUTCOMES = (('delivered', 'returned the field', '#2f8f5b'), ('missing', 'found the item, field missing', '#e4b35c'),
            ('no_target', 'did not find the item', '#d3d8d5'), ('error', 'run failed', '#c4443a'))
LABELS = {'reviews_count': 'review count', 'bestseller_rank': 'bestseller rank', 'image_url': 'image', 'specifications': 'specs',
          'followers_count': 'followers', 'following_count': 'following', 'posts_count': 'posts', 'external_url': 'link',
          'is_verified': 'verified', 'full_name': 'name', 'latest_post_url': 'post URL', 'latest_post_caption': 'post caption',
          'latest_post_likes': 'post likes', 'latest_post_comments': 'post comments'}
PANELS = (('claims', 'Claimed fields', (0, 10.4), (0, 5, 10), ''), ('unsupported', 'Unsupported claims', (0, 6), (0, 3, 6), ''),
          ('similarity', 'Similarity', (0, 1.04), (0, 0.5, 1), ''),
          ('first', 'First-listed share', (0, 104), (0, 50, 100), '%'), ('success', 'Task success', (0, 104), (0, 50, 100), '%'))
MORE = (('overclaims', 'Overclaimed fields', (0, 7.3), (0, 3, 6), ''), ('best', 'Sent to the most capable tool', (0, 104), (0, 50, 100), '%'),
        ('lost_capable', 'Lost to capable tools', (0, 52), (0, 25, 50), '%'), ('lost_weak', 'Lost to weak tools', (0, 52), (0, 25, 50), '%'))
SMOOTH = 3  # rounds in the centred moving average drawn for every curve after round zero

plt.rcParams.update({'font.family': 'STIXGeneral', 'mathtext.fontset': 'stix', 'font.size': 7, 'pdf.fonttype': 42,
                     'savefig.bbox': 'tight', 'savefig.pad_inches': 0.03,  # keep labels at the figure edge inside the page
                     'axes.linewidth': 0.5})


def smooth(values):
    """Centred moving average over SMOOTH rounds, shorter at the ends; round zero, before any rewrite, is kept as measured."""
    half = SMOOTH // 2
    return values[:1] + [statistics.mean(values[max(1, t - half):t + half + 1]) for t in range(1, len(values))]


def trend(ax, curves, seller):
    """One seller model's markets: their smoothed mean as a line, and the range between them as a band."""
    rows = [smooth(values) for (_, s), values in curves.items() if s == seller]
    x, colour = range(len(rows[0])), COLOURS[seller]
    ax.fill_between(x, [min(v) for v in zip(*rows)], [max(v) for v in zip(*rows)], color=colour, alpha=0.18, lw=0)
    ax.plot(x, [statistics.mean(v) for v in zip(*rows)], color=colour, lw=1.2, solid_capstyle='round')


def axis(ax, ylim, ticks, unit='', labelsize=6.3):
    ax.set(ylim=ylim, yticks=ticks, xticks=range(0, ROUNDS, 5), xlim=(-0.25, ROUNDS - 0.75))
    ax.set_yticklabels([f'{t:g}{unit}' if t == ticks[-1] else f'{t:g}' for t in ticks])
    ax.tick_params(length=2, width=0.5, colors=MUTED, pad=2, labelsize=labelsize)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        ax.spines[side].set_color(RULE)


def box(ax, y, h, title, body, fill=PANEL):
    ax.add_patch(FancyBboxPatch((0.13, y), 0.87, h, boxstyle='round,pad=0,rounding_size=0.025', fc=fill, ec=RULE, lw=0.6))
    ax.text(0.565, y + h * 0.62, title, ha='center', va='center', weight='bold', color=INK)
    ax.text(0.565, y + h * 0.27, body, ha='center', va='center', color=MUTED, fontsize=5.8)


def arrow(ax, a, b, label=None):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle='-|>', mutation_scale=6, lw=0.7, color=MUTED, shrinkA=0, shrinkB=0))
    if label:
        ax.text(a[0] + 0.03, (a[1] + b[1]) / 2, label, ha='left', va='center', color=MUTED, fontsize=5.8, style='italic')


def market(ax):
    """The market as a loop: sellers rewrite, buyers select, the matrix scores, and selection counts go back to sellers."""
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis('off')
    box(ax, 0.80, 0.17, 'Seller agents', 'one per tool')
    box(ax, 0.54, 0.17, 'Tool descriptions', 'all that buyers see', fill='white')
    box(ax, 0.28, 0.17, 'Buyer agents', 'one tool per question')
    box(ax, 0.02, 0.17, 'Ground truth', 'every tool executed')
    for top, bottom, label in ((0.80, 0.71, 'rewrite'), (0.54, 0.45, 'select'), (0.28, 0.19, 'score')):
        arrow(ax, (0.565, top), (0.565, bottom), label)
    ax.plot([0.13, 0.055, 0.055], [0.365, 0.365, 0.885], color=MUTED, lw=0.7, solid_capstyle='butt')
    arrow(ax, (0.055, 0.885), (0.13, 0.885))
    ax.text(0.015, 0.625, 'selection counts', rotation=90, ha='center', va='center', color=MUTED, fontsize=5.8, style='italic')


def fields(ax, amazon):
    """Final-round claims of every Amazon tool under mild and severe toolflation: one dot per tool and field."""
    ax.axis('off')
    ax.set_aspect('equal')
    width = len(amazon.fields)
    for k, seller in enumerate(('codex', 'gemini')):
        left, colour = k * (width + 2.5), COLOURS[seller]
        ax.plot([left - 0.4, left + width - 0.6], [-1.1, -1.1], color=colour, lw=2, solid_capstyle='butt')
        ax.text(left - 0.4, -1.5, name(seller), color=INK, va='bottom', fontsize=6.5)
        unsupported = 0
        for y, tool in enumerate(amazon.codes):
            claimed, shown = set(amazon.description(('claude', seller, 'neutral', 0), ROUNDS - 1, tool)['claims']), amazon.evidence[tool]
            unsupported += len(claimed - shown)
            for x, field in enumerate(amazon.fields):
                if field not in claimed:
                    ax.scatter(left + x, y, s=1.2, color=RULE, lw=0)
                else:
                    ax.scatter(left + x, y, s=13, color=UNSUPPORTED if field not in shown else SUPPORTED, lw=0)
            if k == 0:
                ax.text(-1.0, y, tool, ha='right', va='center', fontsize=6.3, color=INK)
        ax.text(left + width / 2 - 0.5, len(amazon.codes) + 0.3, f'{unsupported} unsupported', ha='center', va='top', fontsize=6.3, color=UNSUPPORTED)
    ax.set(xlim=(-2.6, 2 * width + 2.2), ylim=(len(amazon.codes) + 1.6, -2.2))
    handles = [plt.Line2D([], [], marker='o', ls='', ms=3.3, color=c, label=l) for c, l in
               ((SUPPORTED, 'claimed and returned'), (UNSUPPORTED, 'claimed but not returned'))]
    ax.legend(handles=handles, loc='lower center', bbox_to_anchor=(0.5, -0.24), ncol=2, frameon=False, fontsize=6.3,
              handletextpad=0.2, columnspacing=1.2)


def success(ax, amazon):
    curves = amazon.series('success')
    for seller in SELLERS:
        trend(ax, curves, seller)
    random, ceiling = amazon.baselines()
    for level, label, x, ha in ((ceiling, 'best choice', ROUNDS - 0.9, 'right'), (random, 'random choice', 0.3, 'left')):  # the legend sits below the random line
        ax.axhline(level, color=MUTED, lw=0.6, ls=(0, (3, 2)))
        ax.text(x, level + 1, label, color=MUTED, fontsize=5.8, va='bottom', ha=ha, style='italic', bbox=dict(fc='white', ec='none', pad=0.3))
    ax.text(5.2, 52, MODELS['gemini'], color=COLOURS['gemini'], fontsize=6.3, ha='left', va='center')  # direct labels: five legend rows would cover the curves
    ax.text(ROUNDS - 1, 83, 'the other four\nseller agents', color=MUTED, fontsize=6.3, ha='right', va='top', linespacing=1.0)
    axis(ax, (0, 108), (0, 25, 50, 75, 100), '%', labelsize=7)
    ax.set_xlabel('round of rewriting', color=MUTED, labelpad=2)


def overview(out, amazon):
    figure = plt.figure(figsize=(5.5, 2.25))
    for x, title in ((0.0, '(a) The market'), (0.29, '(b) Fields claimed by the ten Amazon tools'), (0.76, '(c) Buyer task success')):
        figure.text(x, 0.995, title, weight='bold', va='top', fontsize=7.2)
    market(figure.add_axes([0.008, 0.0, 0.25, 0.90]))
    fields(figure.add_axes([0.28, 0.09, 0.46, 0.84]), amazon)
    success(figure.add_axes([0.80, 0.15, 0.195, 0.76]), amazon)
    figure.savefig(out)


def capability(out, shelf):
    """What each tool returned for every question: one dot per target and field, and each tool's outcome shares."""
    tools, targets, verdict = shelf.codes, shelf.targets, shelf.verdict
    share = lambda tool, kind: sum(verdict[tool, x, f] == kind for x in targets for f in shelf.fields) / (len(targets) * len(shelf.fields))
    fields = sorted(shelf.fields, key=lambda f: -sum(verdict[t, x, f] == 'delivered' for t in tools for x in targets))
    colours = {kind: colour for kind, _, colour in OUTCOMES}
    figure = plt.figure(figsize=(5.5, 2.35))
    ax = figure.add_axes([0.06, 0.1, 0.84, 0.74])
    cols, rows, dot, gap = 6, 5, 0.13, 0.03  # one field holds the 30 targets as a 6 x 5 block of dots
    width, height = cols * dot + (cols - 1) * gap, rows * dot + (rows - 1) * gap
    for y, tool in enumerate(tools):
        for x, field in enumerate(fields):
            for k, target in enumerate(targets):
                ax.add_patch(plt.Rectangle((x * 1.2 + (k % cols) * (dot + gap), y * 1.1 + (k // cols) * (dot + gap)), dot, dot,
                                           lw=0, color=colours[verdict[tool, target, field]]))
        left = len(fields) * 1.2 + 0.25
        for kind, _, colour in OUTCOMES:  # the tool's outcome shares as one stacked bar
            part = 2.6 * share(tool, kind)
            ax.add_patch(plt.Rectangle((left, y * 1.1 + 0.2), part, height - 0.4, lw=0, color=colour))
            left += part
        ax.text(len(fields) * 1.2 + 3.0, y * 1.1 + height / 2, f'{fmt(100 * share(tool, "delivered"))}%', ha='left', va='center', fontsize=6.5, color=INK)
        ax.text(-0.25, y * 1.1 + height / 2, tool, ha='right', va='center', fontsize=6.5, color=INK, linespacing=0.95)
    for x, field in enumerate(fields):
        ax.text(x * 1.2 + width / 2, -0.35, LABELS.get(field, field.replace('_', ' ')), ha='left', va='bottom', rotation=35, fontsize=6.5, color=INK)
    ax.text(len(fields) * 1.2 + 0.25, -0.35, 'all questions', ha='left', va='bottom', fontsize=6.5, color=MUTED)
    ax.set_xlim(-0.1, len(fields) * 1.2 + 3.6)
    ax.set_ylim(len(tools) * 1.1, -0.1)
    ax.axis('off')
    handles = [plt.Rectangle((0, 0), 1, 1, color=colour, lw=0) for _, _, colour in OUTCOMES]
    figure.legend(handles, [label for _, label, _ in OUTCOMES], loc='lower center', ncol=4, frameon=False, fontsize=6.5,
                  handlelength=0.8, handleheight=0.8, handletextpad=0.4, columnspacing=1.4, bbox_to_anchor=(0.5, -0.02))
    figure.savefig(out)


def dynamics(out, shelves, panels=PANELS, height=2.15, raw=False):
    """One row per platform, one colour per seller model: what sellers write, then what buyers do. Each seller model is drawn
    as the smoothed mean of its markets with their range, or with raw=True as one unsmoothed line per market."""
    figure, axes = plt.subplots(len(shelves), len(panels), figsize=(5.5, height), sharex=True)
    for i, (row, shelf) in enumerate(zip(axes, shelves)):
        for ax, (key, heading, ylim, ticks, unit) in zip(row, panels):
            curves = shelf.series(key)
            for seller in SELLERS:
                if raw:
                    for (_, s), values in curves.items():
                        if s == seller:
                            ax.plot(range(len(values)), values, color=COLOURS[seller], lw=1.0, solid_capstyle='round')
                else:
                    trend(ax, curves, seller)
            for level in {'first': (10,), 'success': shelf.baselines()}.get(key, ()):
                ax.axhline(level, color=MUTED, lw=0.6, ls=(0, (3, 2)), zorder=0)
            axis(ax, ylim, ticks, unit)
            if i == 0:
                ax.set_title(heading, loc='left', fontsize=6.8, weight='bold', pad=4)
        row[0].set_ylabel(PLATFORMS[shelf.name], color=INK, fontsize=6.8, weight='bold', labelpad=3)
    for ax in axes[-1]:
        ax.set_xlabel('round of rewriting', color=MUTED, fontsize=6.3, labelpad=2)
    handles = [plt.Line2D([], [], color=COLOURS[k], lw=1.6, label=name(k)) for k in SELLERS]
    if any(key in ('first', 'success') for key, *_ in panels):
        handles.append(plt.Line2D([], [], color=MUTED, lw=0.6, ls=(0, (3, 2)), label='reference levels'))
    figure.legend(handles=handles, loc='upper center', ncol=3, frameon=False, fontsize=6.3, handlelength=1.6, columnspacing=1.2,
                  bbox_to_anchor=(0.53, 1.0), labelspacing=0.3)
    figure.subplots_adjust(left=0.085, right=0.995, top=1 - 0.5 / height, bottom=0.105 * 2.2 / height, wspace=0.3, hspace=0.3)
    figure.savefig(out)


def palette(shelf):
    """Colours of the tools from the most capable to the least: blues by capability, the weak tools in orange."""
    strong = [t for t in shelf.codes if t not in shelf.weak]
    return {t: BLUES(0.92 - 0.75 * strong.index(t) / max(len(strong) - 1, 1)) if t in strong
            else plt.get_cmap('Oranges')(0.75 - 0.15 * (shelf.codes.index(t) - len(strong))) for t in shelf.codes}


def stack(ax, shelf, market):
    """Smoothed share of choices per tool and round in one market, averaged over its seeds, the most capable tool at the bottom."""
    colours, seeds = palette(shelf), shelf.runs()[market]
    stacks = [smooth([statistics.mean(100 * seed[i]['selections'][t] / seed[i]['questions'] for seed in seeds) for i in range(ROUNDS)])
              for t in shelf.codes]
    ax.stackplot(range(ROUNDS), stacks, colors=[colours[t] for t in shelf.codes], lw=0)
    axis(ax, (0, 100), (0, 50, 100), '%')
    ax.set_xlim(0, ROUNDS - 1)


def shares(out, shelves, buyer='claude'):
    """Where one buyer's choices go in every market, one row per platform and one column per seller model."""
    figure, axes = plt.subplots(len(shelves), len(SELLERS), figsize=(5.5, 2.3), sharex=True, sharey=True)
    for i, (row, shelf) in enumerate(zip(axes, shelves)):
        for ax, seller in zip(row, SELLERS):
            stack(ax, shelf, (buyer, seller))
            if i == 0:
                ax.set_title(f'{MODELS[seller]}\n{HARNESSES[seller]}', loc='left', fontsize=6.8, weight='bold', pad=4)
        row[0].set_ylabel(PLATFORMS[shelf.name], color=INK, fontsize=6.8, weight='bold', labelpad=3)
    for ax in axes[-1]:
        ax.set_xlabel('round of rewriting', color=MUTED, fontsize=6.3, labelpad=2)
    keys = [plt.Rectangle((0, 0), 1, 1, fc=BLUES(0.92), label='most capable tool'),
            plt.Rectangle((0, 0), 1, 1, fc=BLUES(0.3), label='other tools, by capability'),
            plt.Rectangle((0, 0), 1, 1, fc=plt.get_cmap('Oranges')(0.65), label='weak tools (under 10% of questions)')]
    figure.legend(handles=keys, loc='upper center', ncol=3, frameon=False, fontsize=6.3, handlelength=1.2, columnspacing=1.6, bbox_to_anchor=(0.53, 1.0))
    figure.subplots_adjust(left=0.085, right=0.995, top=0.8, bottom=0.1, wspace=0.12, hspace=0.3)
    figure.savefig(out)


def outcomes(out, shelves):
    """Task success in every market, from the vendors' descriptions (round zero) to the mean of the last five rounds, one
    arrow per market, between a random choice and the best choice on the shelf."""
    figure, axes = plt.subplots(1, len(shelves), figsize=(5.5, 1.75), sharey=True)
    for ax, shelf in zip(axes, shelves):
        runs, (random, ceiling) = shelf.runs(), shelf.baselines()
        success = lambda parts: statistics.mean(statistics.mean(r['success'] for r in p) for p in parts)
        labels = []
        for y, (seller, buyer) in enumerate((seller, buyer) for seller in SELLERS for buyer in BUYERS):
            y += 0.6 * (y // 2)  # a gap between the groups of two buyers
            seeds = runs[buyer, seller]
            start, end = success([r[:1] for r in seeds]), success([r[-5:] for r in seeds])
            colour = COLOURS[seller]
            ax.plot((start, end), (y, y), color=colour, lw=1.1, solid_capstyle='butt', zorder=2)
            ax.plot(start, y, 'o', ms=3.6, mfc='white', mec=MUTED, mew=0.8, zorder=3)
            ax.plot(end, y, '>' if end >= start else '<', ms=4.2, color=colour, mec='white', mew=0.3, zorder=4)  # points the way success moved
            labels.append((y, seller, buyer))
        for level, text in ((random, 'random choice'), (ceiling, 'best choice')):
            ax.axvline(level, color=MUTED, lw=0.6, ls=(0, (3, 2)), zorder=0)
            ax.text(level, -1.1, text, ha='center', va='bottom', fontsize=5.8, color=MUTED)
        ax.set_xlim(20, 100)
        ax.set_xticks((25, 50, 75, 100))
        ax.set_xticklabels(('25', '50', '75', '100%'))
        ax.tick_params(axis='x', length=2, width=0.5, colors=MUTED, pad=2, labelsize=6.3)
        ax.tick_params(axis='y', length=0, pad=2, labelsize=6.0, colors=INK)
        ax.set_yticks([y for y, _, _ in labels])
        ax.set_yticklabels([HARNESSES[buyer] for _, _, buyer in labels])
        ax.set_ylim(labels[-1][0] + 0.7, -0.9)
        for side in ('top', 'right', 'left'):
            ax.spines[side].set_visible(False)
        ax.spines['bottom'].set_color(RULE)
        ax.set_title(PLATFORMS[shelf.name], loc='left', fontsize=6.8, weight='bold', pad=9)
        ax.set_xlabel('task success', color=MUTED, fontsize=6.3, labelpad=2)
    for y, seller, _ in labels[::2]:  # seller names left of the buyer names
        axes[0].text(-0.36, y + 0.5, name(seller), transform=blended_transform_factory(axes[0].transAxes, axes[0].transData), ha='right',
                     va='center', fontsize=6.0, color=COLOURS[seller], weight='bold')
    handles = [plt.Line2D([], [], marker='o', ms=3.6, mfc='white', mec=MUTED, mew=0.8, lw=0), plt.Line2D([], [], color=INK, lw=0, marker='>', ms=4.2)]
    figure.legend(handles, ["vendors' descriptions (round 0)", 'last five rounds'], loc='upper center', ncol=2, frameon=False, fontsize=6.0,
                  handletextpad=0.4, columnspacing=1.2, bbox_to_anchor=(0.6, 1.0))
    figure.subplots_adjust(left=0.43, right=0.99, top=0.8, bottom=0.15, wspace=0.12)
    figure.savefig(out)


def main(directory):
    directory.mkdir(parents=True, exist_ok=True)
    shelves = [Shelf(p) for p in PLATFORMS]
    overview(directory / 'overview.pdf', shelves[0])
    for shelf in shelves:
        capability(directory / f'capability-{shelf.name}.pdf', shelf)
    dynamics(directory / 'dynamics.pdf', shelves, height=1.95)
    dynamics(directory / 'metrics.pdf', shelves, MORE)
    dynamics(directory / 'raw.pdf', shelves, raw=True)
    shares(directory / 'shares.pdf', shelves)
    outcomes(directory / 'outcomes.pdf', shelves)


if __name__ == '__main__':
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else data.ROOT / 'out')
