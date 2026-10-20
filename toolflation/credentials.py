# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""Credentials. Provider keys come from a JSON file, api_keys.json next to the repository unless TOOLFLATION_KEYS names
another. The Vertex AI models run in GOOGLE_CLOUD_PROJECT, else in the project of the application default credentials."""
import json
import os
from pathlib import Path

KEYS = Path(os.getenv('TOOLFLATION_KEYS', Path(__file__).resolve().parents[2] / 'api_keys.json'))


def key(name):
    return json.loads(KEYS.read_text())[name]


def project():
    import google.auth
    return os.getenv('GOOGLE_CLOUD_PROJECT') or google.auth.default()[1]
