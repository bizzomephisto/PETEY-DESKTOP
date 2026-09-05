"""Shared, bounded HTTP connection pool for synchronous provider clients."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter


SESSION = requests.Session()
_ADAPTER = HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=0, pool_block=True)
SESSION.mount("https://", _ADAPTER)
SESSION.mount("http://", _ADAPTER)
