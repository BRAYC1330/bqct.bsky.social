import logging
import re
import config
import generator
import bsky
import utils
from link_extractor import LinkExtractor
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    try:
        uri = task.get("uri", "")
        text = task.get("text", "")
        if not uri or not text:
            return
        
        text = text.replace("!c", "").replace("!t", "").strip()
        if not text:
            return

        chain = await bsky.fetch_thread_chain(client, uri)
        if not chain:
            return
            
        link_extractor = LinkExtractor()
        link_content_parts = []
        
        for post in chain.get("chain", []):
            post_text = post.get("record", {}).get("text", "")
            urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', post_text)
            for url in urls:
                content = await link_extractor.extract(url)
                if content:
                    link_content_parts.append(f"[Linked content from {url}]: {content}")
                    
        if link_content_parts:
            text += "\n\n" + "\n\n".join(link_content_parts)

        root_uri = chain.get("root_uri", uri)
        root_cid = chain.get("root_cid", "")
        parent_uri = uri
        parent_cid = chain.get("parent_cid", "")
        
        reply = generator.get_reply(llm, "", "", "", text)
        if not reply or reply == "Error generating reply.":
            return
            
        await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, parent_uri, parent_cid)
    except Exception as e:
        logger.error(f"Community process failed: {e}")