import logging
import generator
import search
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    if not task.get("parent_uri"):
        logger.warning(f"[community] Missing parent_uri for {task['uri']}")
        return
    
    uri = task["uri"]
    user_text = task["text"]
    
    keyword_prompt = f"Extract the main crypto/tech keyword or topic from this comment. Return ONLY the keyword, nothing else.\nComment: \"{user_text}\"\nKeyword:"
    try:
        kw_response = llm(keyword_prompt, max_tokens=20, temperature=0.1)
        keyword = kw_response["choices"][0]["text"].strip()
        if not keyword or len(keyword) > 50:
            keyword = user_text[:30]
    except:
        keyword = user_text[:30]
    
    search_data = await search.fetch_chainbase(keyword)
    
    chain = await utils._fetch_thread_chain_internal(client, uri)
    if not chain:
        return
    
    root_uri = chain.get("root_uri", task.get("parent_uri", uri))
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    
    import state
    import parser as ctx_parser
    import bsky
    import config
    
    memory = state.load_context(root_uri)
    root_thread = f"Root: {chain.get('root_text', '')[:200]}"
    final_ctx = ctx_parser.prepare_context(memory, root_thread, search_data, user_text)
    
    reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=280, temperature=0.7)
    if utils.count_graphemes(reply) > 293:
        reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=260, temperature=0.7)
    if utils.count_graphemes(reply) > 293:
        return
    
    if search_data and search_data.strip():
        suffix = "\n\nQwen | Chainbase"
    else:
        suffix = "\n\nQwen"
        if len(reply) < 50:
            reply = reply + " Please clarify your question for better results."
    
    reply = reply.strip() + suffix
    
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    
    if root_uri != utils._get_active_digest_uri():
        state.save_context(root_uri, generator.update_summary(llm, memory, user_text, reply))
    
    logger.info(f"[community] Replied to {uri[:40]}...")