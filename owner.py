import logging
import re
import config
import bsky
import generator
import search
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    search_data = ""
    source = ""
    
    if do_search:
        clean_text = re.sub(r'(!t|!c)', '', user_text, flags=re.I).strip()
        if "!c" in user_text.lower():
            kw = generator.extract_chainbase_keyword(llm, clean_text)
            if kw:
                search_data = await search.fetch_chainbase(kw)
                source = "chainbase"
        else:
            q, t = generator.extract_search_intent(llm, "", clean_text)
            if q:
                search_data = await search.fetch_tavily(q, t)
                source = "tavily"
    
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return
    
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    
    thread_ctx = await utils._format_thread_for_llm(chain, config.OWNER_DID, config.BOT_DID, client)
    
    sig = "\n\nQwen"
    if source == "tavily" and search_data:
        sig = "\n\nQwen | Tavily"
    elif source == "chainbase" and search_data:
        sig = "\n\nQwen | Chainbase"
    max_body = 300 - len(sig)
    
    ctx = thread_ctx
    if search_data:
        ctx += f"\n\n[SEARCH]\n{search_data}"
    
    reply = generator.get_answer(llm, ctx, user_text, max_chars=max_body, temperature=0.3)
    
    if utils.count_graphemes(reply) > max_body:
        truncated = reply[:max_body]
        last_dot = truncated.rfind(".")
        reply = truncated[:last_dot+1] if last_dot != -1 else truncated.rstrip() + "."
    
    final = reply.strip() + sig
    
    await bsky.post_reply(client, config.BOT_DID, final, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[owner] Replied to {uri[:40]}...")