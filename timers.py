import os
import logging
from datetime import datetime, timezone
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def check_timer(secret_name: str, hours: int) -> bool:
    logger.debug(f"[check_timer] Checking {secret_name} (threshold: {hours}h)")
    secret_value = os.getenv(secret_name, "").strip()
    if not secret_value or secret_value.lower() in ("", "{}", "null", "none", "''", '""'):
        logger.debug(f"[check_timer] {secret_name} is empty/invalid -> due=True")
        return True
    try:
        val = secret_value.strip('"').strip("'")
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        last = datetime.fromisoformat(val)
        now = datetime.now(timezone.utc)
        diff_hours = (now - last).total_seconds() / 3600
        is_due = diff_hours >= hours
        logger.debug(f"[check_timer] {secret_name}: last={val}, diff={diff_hours:.2f}h, due={is_due}")
        return is_due
    except Exception as e:
        logger.warning(f"[check_timer] {secret_name} parse error: {e} -> due=True")
        return True

def check_mini_timer() -> bool:
    return check_timer("LAST_MINI_DIGEST", 4)

def check_full_timer() -> bool:
    return check_timer("LAST_FULL_DIGEST", 2)
