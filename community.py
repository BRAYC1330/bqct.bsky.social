import logging
import config
import generator
import bsky
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    try:
        uri = task.get("uri", "")
        text = task.get("text", "")
        if not uri or not text:
            return
        chain = await bsky.fetch_thread_chain(client, uri)
        if not chain:
            return
        root_uri = chain.get("root_uri", uri)
        root_cid = chain.get("root_cid", "")
        parent_uri = uri
        parent_cid = chain.get("parent_cid", "")
        
        reply = generator.get_reply(llm, "", "", "", text)
        if not reply or reply == "Error generating reply.":
            return
            
        await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, parent_uri, parent_cid)
        logger.info("[COMMUNITY] Reply posted successfully.")
    except Exception as e:
        logger.error(f"[COMMUNITY] process failed: {e}")