import logging
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    if not task.get("parent_uri"):
        logger.warning(f"[community] Missing parent_uri for {task['uri']}")
        return
    await utils.process_reply(client, llm, task, max_chars=280, suffix="\n\nQwen", temperature=0.7)