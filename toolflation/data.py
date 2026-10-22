# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""The dataset: the released tables on Hugging Face, and reading and writing them.

python -m toolflation.data   # downloads the pinned release into data/

data/<platform>/ holds tools.json, shelf.json, targets.json, fields.json, questions.json, and one row per line in
matrix.jsonl, descriptions.jsonl, choices.jsonl and rewrites.jsonl; data/judges.json holds the second claims judge.
Raw logs that the released tables leave out (tool outputs, agent sessions) go to raw/."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA, RAW = ROOT / 'data', ROOT / 'raw'
REPO, REVISION = 'lilvjosephtang/Toolflation', 'bcaa0ad996a8f8721ff9da9fc098df0fbc87c453'
MARKET = ('buyer', 'seller', 'objective', 'seed')  # the columns that name a market


def read(path):
    path = Path(path)
    if path.suffix == '.jsonl':
        return [json.loads(line) for line in path.read_text().split('\n') if line] if path.exists() else []  # U+2028 in scraped text is no line break
    return json.loads(path.read_text())


def write(path, value):
    """A list of rows to .jsonl, anything else to indented .json."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.jsonl':
        path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in value))
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def append(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as out:
        out.writelines(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)


def market(row):
    """The market a row belongs to: (buyer, seller, objective, seed)."""
    return tuple(row[k] for k in MARKET)


def load(platform, directory=DATA):
    """Every table of one platform, by file name."""
    names = ('tools', 'shelf', 'targets', 'fields', 'questions', 'matrix', 'descriptions', 'choices', 'rewrites')
    return {name: read(next(p for p in (directory / platform / f'{name}.json', directory / platform / f'{name}.jsonl') if p.exists()))
            for name in names}


def download(directory=DATA):
    from huggingface_hub import snapshot_download
    snapshot_download(REPO, repo_type='dataset', revision=REVISION, local_dir=directory)


if __name__ == '__main__':
    download()
