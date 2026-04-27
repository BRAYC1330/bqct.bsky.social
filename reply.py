import hashlib
import logging
import re
import config
import bsky
import utils
import state
import generator
from link_extractor import LinkExtractor
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

async def process_reply(client, llm, task, max_chars=240, suffix="", temperature=0.7, search_data="", link_content=""):
    uri = task["uri"]
    user_text = utils.sanitize_input(task["text"])
    user_text = user_text.replace("!c", "").replace("!t", "").strip()
    logger.info(f"START | uri={uri} | user_text={user_text}")
    
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
    
    root_uri = chain.get("root_uri", task.get("parent_uri", uri))
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("cid", "")
    
    root_thread = utils.sanitize_input(chain.get("root_text", ""))
    full_thread_text = utils.sanitize_input(chain.get("full_text", ""), max_len=4000)
    
    ext = LinkExtractor()
    full_link_content = []
    
    if link_content:
        full_link_content.append(link_content)
        
    for post in chain.get("chain", []):
        post_text = post.get("record", {}).get("text", "")
        urls = URL_PATTERN.findall(post_text)
        for url in urls:
            content = await ext.extract(url)
            if content:
                full_link_content.append(f"[Linked content from {url}]: {content}")
                
    await ext.close()

    combined_link_content = "\n\n".join(full_link_content) if full_link_content else ""
    
    current_hash = hashlib.sha256(full_thread_text.encode()).hexdigest()
    cached_mem, stored_hash = state.load_context(root_uri)
    
    logger.info(f"THREAD_HASH_CURRENT: {current_hash}")
    logger.info(f"THREAD_HASH_STORED: {stored_hash or 'NONE'}")
        
    if stored_hash == current_hash and cached_mem:
        final_context = cached_mem
        logger.info("CACHE_STATUS: HIT")
    else:
        final_context = generator.update_context_memory(llm, full_thread_text)
        state.save_context(root_uri, final_context, current_hash)
        logger.info("CACHE_STATUS: MISS")
            
    combined_search = utils.sanitize_input(search_data)
    if combined_link_content:
        combined_search = f"{combined_search}\n\n[EXTRACTED_LINKS]\n{utils.sanitize_input(combined_link_content)}" if combined_search else f"[EXTRACTED_LINKS]\n{utils.sanitize_input(combined_link_content)}"
        
    logger.info(f"Full search \n{combined_search}")
    reply = generator.get_reply(llm, final_context, root_thread, combined_search, user_text)
    reply = utils.validate_and_fix_output(reply)
    
    max_body = max_chars - len(suffix)
    if utils.count_tokens(reply, llm) > int(max_body * config.TOKEN_TO_CHAR_RATIO):
        reply = reply[:max_body].rsplit(" ", 1)[0] + "."
    if len(reply) > max_body:
        reply = reply[:max_body].rsplit(".", 1)[0] + "." if "." in reply[:max_body] else reply[:max_body-3] + "..."
        
    final_reply = reply + suffix
    is_valid, trimmed = utils.validate_post_content(final_reply, max_graphemes=280)
    if not is_valid:
        logger.warning("Reply exceeded limit, trimmed")
        final_reply = trimmed
        
    logger.info(f"Final reply ({len(final_reply)} chars):\n{final_reply}")
    logger.info(f"Sending reply | root_uri={root_uri} | parent_uri={uri}")
    await bsky.post_reply(client, config.BOT_DID, final_reply, root_uri, root_cid, uri, parent_cid)