import os
import logging
import config
import utils
import generator
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

OVERFLOW_THRESHOLD = 400
CHUNK_MARKERS = ["[CH:0/2]", "[CH:1/2]", "[CH:2/2]"]

def _get_slots(thread_id: str) -> list:
    base = utils.hash_to_slot(thread_id, config.CONTEXT_SLOT_COUNT)
    return [base, (base + 1) % config.CONTEXT_SLOT_COUNT, (base + 2) % config.CONTEXT_SLOT_COUNT]

def load_context(thread_id: str) -> str:
    slots = _get_slots(thread_id)
    parts = []
    for i, slot in enumerate(slots):
        val = os.getenv(f"CONTEXT_{slot}", "").strip()
        if not val: continue
        if val.startswith(CHUNK_MARKERS[i]):
            parts.append(val[len(CHUNK_MARKERS[i]):])
        elif i == 0:
            return val
        else:
            break
    if not parts: return ""
    return " ".join(parts)

def save_context(thread_id: str, llm, history: str):
    if not history: return
    memory = generator.update_context_memory(llm, history)
    if not memory: return
    slots = _get_slots(thread_id)
    if len(memory) > OVERFLOW_THRESHOLD:
        chunk_len = (len(memory) + 2) // 3
        utils.update_github_secret(f"CONTEXT_{slots[0]}", f"{CHUNK_MARKERS[0]}{memory[:chunk_len]}")
        utils.update_github_secret(f"CONTEXT_{slots[1]}", f"{CHUNK_MARKERS[1]}{memory[chunk_len:chunk_len*2]}")
        utils.update_github_secret(f"CONTEXT_{slots[2]}", f"{CHUNK_MARKERS[2]}{memory[chunk_len*2:]}")
        logger.debug(f"[state] Context split across slots {slots}")
    else:
        utils.update_github_secret(f"CONTEXT_{slots[0]}", memory)
        logger.debug(f"[state] Context saved to slot {slots[0]}")