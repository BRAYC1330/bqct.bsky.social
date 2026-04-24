import logging
import generator
import search
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    if not task.get("parent_uri"):
        logger.warning("[community] Missing parent_uri")
        return
    user_text = task["text"]
    keyword = generator.extract_chainbase_keyword(llm, user_text)
    search_data = await search.fetch_chainbase(keyword)
    await utils.process_reply(client, llm, task, max_chars=240, suffix="\n\nQwen | Chainbase", temperature=0.7, search_data=search_data if search_data else None)