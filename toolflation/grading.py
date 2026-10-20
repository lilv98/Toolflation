# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""Grading by fixed rules, without a model: value checks for the platform modules, and the verdicts of one run."""
import re
import unicodedata
from urllib.parse import urlparse

CELLS = ('delivered', 'missing', 'no_target', 'error')


def service_error(items):
    """Some actors report an outage as a dataset row instead of a failed run."""
    messages = [item.get('error_message') or item.get('error') for item in items if isinstance(item, dict)]
    return messages[0] if items and all(messages) else None


def tokens(value):
    value = unicodedata.normalize('NFKD', str(value or '')).casefold()
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.findall(r'[a-z]+|[0-9]+', value)


def first(record, keys):
    """The first non-empty value among alias keys."""
    return next((record[key] for key in keys if record.get(key) not in (None, '', [], {})), None)


def is_url(value):
    url = urlparse(str(value)) if isinstance(value, str) else None
    return bool(url and url.scheme in ('http', 'https') and url.hostname)


def number(value, low, high):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high


def integer(value, low=0, high=1e12):
    return number(value, low, high) and float(value).is_integer()


def text(value, minimum=1):
    return isinstance(value, str) and len(value.strip()) >= minimum


def classify(platform, run, target, fields):
    """The verdict for every field of one run of a tool on a target."""
    if run['error'] or service_error(run['items']):
        return {f: 'error' for f in fields}
    rows = [platform.canonical(item) for item in run['items'] if isinstance(item, dict)]
    hits = [row for row in rows if platform.is_target(row, target)]
    if not hits:
        return {f: 'no_target' for f in fields}
    return {f: 'delivered' if any(platform.delivered(f, row[f]) for row in hits) else 'missing' for f in fields}
