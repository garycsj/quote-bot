"""whitelist.py — Persistent Telegram user whitelist.

Stores authorized user IDs in a JSON file. Prefers `/data/whitelist.json`
(Railway Volume) for persistence across deploys; falls back to a file
next to this module when no volume is mounted (useful for local dev,
but will not survive a Railway redeploy).
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path('/data') if Path('/data').is_dir() else Path(__file__).parent
_WHITELIST_PATH = _DATA_DIR / 'whitelist.json'
_bootstrapped = False


def _read() -> set[int]:
    if not _WHITELIST_PATH.exists():
        return set()
    try:
        data = json.loads(_WHITELIST_PATH.read_text(encoding='utf-8'))
        return {int(uid) for uid in data.get('user_ids', [])}
    except Exception as e:
        logger.error(f'Failed to read whitelist at {_WHITELIST_PATH}: {e}', exc_info=True)
        return set()


def _write(ids: set[int]) -> None:
    _WHITELIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _WHITELIST_PATH.write_text(
        json.dumps({'user_ids': sorted(ids)}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _env_ids() -> set[int]:
    raw = os.environ.get('ALLOWED_USER_IDS', '')
    out: set[int] = set()
    for part in raw.split(','):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def _bootstrap_once() -> None:
    """Merge any IDs from ALLOWED_USER_IDS env into the JSON file (one-time per process)."""
    global _bootstrapped
    if _bootstrapped:
        return
    _bootstrapped = True
    if not _DATA_DIR.exists() or _DATA_DIR == Path(__file__).parent:
        logger.warning(
            'Whitelist persistence dir is not /data — approvals will be lost on redeploy. '
            'Mount a Railway Volume at /data to fix.'
        )
    ids = _read()
    env = _env_ids()
    new = env - ids
    if new:
        _write(ids | env)
        logger.info(f'Whitelist bootstrapped from ALLOWED_USER_IDS: added {sorted(new)}')


def load() -> set[int]:
    _bootstrap_once()
    return _read()


def is_authorized(user_id: int) -> bool:
    return int(user_id) in load()


def add_user(user_id: int) -> None:
    ids = load()
    if int(user_id) in ids:
        return
    ids.add(int(user_id))
    _write(ids)
    logger.info(f'Authorized new user: {user_id}')
