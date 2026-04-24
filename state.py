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

def save_context(thread_id: str, llm, history: str):
    import generator
    if not history:
        return
    memory = load_context(thread_id)
    full_context = f"{memory}\n\n{history}" if memory else history
    new_memory = generator.update_context_memory(llm, full_context)
    
    if new_memory:
        slot = utils.hash_to_slot(thread_id, config.CONTEXT_SLOT_COUNT)
        utils.update_github_secret(f"CONTEXT_{slot}", new_memory)