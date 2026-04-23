import os
import logging
from datetime import datetime, timezone
logger = logging.getLogger(__name__)

MINI_INTERVAL = 4 * 3600
FULL_INTERVAL = 2 * 3600

def _check(last_key, interval):
    last_str = os.getenv(last_key, "").strip()
    if not last_str:
        logger.warning(f"[timers] {last_key} is empty. Returning due=True")
        return True
    try:
        last_dt = datetime.fromisoformat(last_str)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        delta = (datetime.now(timezone.utc) - last_dt).total_seconds()
        is_due = delta >= interval
        logger.info(f"[timers] {last_key} delta={delta:.0f}s, due={is_due}")
        return is_due
    except Exception as e:
        logger.error(f"[timers] {last_key} parse error: {e}. Returning due=True")
        return True

def check_mini_timer():
    return _check("LAST_MINI_DIGEST", MINI_INTERVAL)

def check_full_timer():
    return _check("LAST_FULL_DIGEST", FULL_INTERVAL)
