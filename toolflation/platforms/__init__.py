# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""One module per platform: how to find its tools in the store, ask about its targets, run its tools and grade their output.

Every platform module defines SEARCH, KEYWORDS, NOUN, TARGET, IDENTITY, PRIVATE, PRICE_EXEMPT, JUDGE_NOTE, ALIASES, CAP,
BUILDERS, question(target, field), canonical(record), is_target(row, target) and delivered(field, value)."""
import importlib

NAMES = ('amazon', 'instagram')


def load(name):
    return importlib.import_module(f'{__name__}.{name}')


def questions(platform, targets, fields):
    """One question per target and field, in that order."""
    grid = [(target, field) for target in targets for field in fields]
    return [{'id': f'Q{i:03d}', 'target': target['id'], 'field': field['id'],
             'prompt': f'{platform.question(target, field)} Report the {platform.IDENTITY} together with the requested value.'}
            for i, (target, field) in enumerate(grid, 1)]


def evidence(platform, record, fields):
    """The fields present in an output record."""
    row = platform.canonical(record) if isinstance(record, dict) else {}
    return {f for f in fields if row.get(f) not in (None, '', [], {})}
