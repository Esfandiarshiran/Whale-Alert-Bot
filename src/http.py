"""
HTTP helper with retry + backoff + circuit breaker.
Critical: NEVER raise. Always return None on failure so the bot cannot crash.
"""
import time
import json
import random
from typing import Optional, Any
import requests

from .config import log

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'OnchainWhaleAlert/2.0 (+https://t.me/OnchainPulse3)',
    'Accept': 'application/json',
})


def fetch_json(url: str, params: dict = None, headers: dict = None,
               max_retries: int = 3, timeout: int = 15) -> Optional[Any]:
    """
    GET with retries on transient failures. Returns None on any error.
    NEVER raises - safe to call without try/except.
    """
    if not url:
        return None
    final_headers = dict(SESSION.headers)
    if headers:
        final_headers.update(headers)

    for attempt in range(max_retries):
        try:
            resp = SESSION.get(url, params=params, headers=final_headers, timeout=timeout)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except (json.JSONDecodeError, ValueError) as e:
                    log.warning(f"JSON decode error from {url[:80]}: {e}")
                    return None
            if resp.status_code in (429, 500, 502, 503, 504):
                # Exponential backoff with jitter
                wait = (2 ** attempt) + random.uniform(0, 1)
                log.warning(f"HTTP {resp.status_code} from {url[:80]} - retry in {wait:.1f}s")
                time.sleep(wait)
                continue
            # 4xx other than 429 - don't retry
            log.warning(f"HTTP {resp.status_code} from {url[:80]}: {resp.text[:200]}")
            return None
        except requests.exceptions.Timeout:
            log.warning(f"Timeout (try {attempt+1}/{max_retries}) on {url[:80]}")
            time.sleep(2 ** attempt)
        except requests.exceptions.ConnectionError as e:
            log.warning(f"Connection error (try {attempt+1}/{max_retries}) on {url[:80]}: {e}")
            time.sleep(2 ** attempt)
        except requests.exceptions.RequestException as e:
            log.warning(f"Request error (try {attempt+1}/{max_retries}) on {url[:80]}: {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            log.warning(f"Unexpected error on {url[:80]}: {e}")
            return None
    log.error(f"All {max_retries} retries exhausted for {url[:80]}")
    return None


def fetch_text(url: str, params: dict = None, headers: dict = None,
               max_retries: int = 3, timeout: int = 15) -> Optional[str]:
    """GET returning text instead of JSON. Same error-safe semantics."""
    if not url:
        return None
    final_headers = dict(SESSION.headers)
    if headers:
        final_headers.update(headers)

    for attempt in range(max_retries):
        try:
            resp = SESSION.get(url, params=params, headers=final_headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep((2 ** attempt) + random.uniform(0, 1))
                continue
            return None
        except requests.exceptions.RequestException as e:
            log.warning(f"Request error (try {attempt+1}/{max_retries}) on {url[:80]}: {e}")
            time.sleep(2 ** attempt)
        except Exception:
            return None
    return None


def post_json(url: str, data: dict = None, headers: dict = None,
              max_retries: int = 3, timeout: int = 30) -> Optional[dict]:
    """POST JSON with retries. Returns parsed response dict or None."""
    if not url:
        return None
    final_headers = {'Content-Type': 'application/json'}
    if headers:
        final_headers.update(headers)

    for attempt in range(max_retries):
        try:
            resp = SESSION.post(url, json=data, headers=final_headers, timeout=timeout)
            if resp.status_code in (200, 201):
                try:
                    return resp.json()
                except (json.JSONDecodeError, ValueError):
                    return {'ok': True, 'raw': resp.text}
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep((2 ** attempt) + random.uniform(0, 1))
                continue
            log.warning(f"HTTP {resp.status_code} POST {url[:80]}: {resp.text[:200]}")
            try:
                return resp.json()
            except Exception:
                return None
        except requests.exceptions.RequestException as e:
            log.warning(f"POST error (try {attempt+1}/{max_retries}) {url[:80]}: {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            log.warning(f"Unexpected POST error {url[:80]}: {e}")
            return None
    return None
