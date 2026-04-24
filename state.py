import os
import logging
import config
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def load_context(thread_id: str) -> str:
    slot = utils.hash_to_slot(thread_id, config.CONTEXT_SLOT_COUNT)
    return os.getenv(f"CONTEXT_{slot}", "") or ""

def save_context(thread_id: str, memory: str):
    slot = utils.hash_to_slot(thread_id, config.CONTEXT_SLOT_COUNT)
    if memory:
        utils.update_github_secret(f"CONTEXT_{slot}", memory[:250])