import logging
import config
import bsky
import generator
import search
import utils
import build_content
logger = logging.getLogger(__name__)

async def _classify_intent(llm, user_text: str, parent_ctx: str) -> str:
    """
    Returns: 'social' or 'search'
    """
    prompt = (f"Analyze the user's reply in the context of the parent post.\n"
              f"Parent post context: {parent_ctx[:200]}...\n"
              f"User reply: \"{user_text}\"\n\n"
              f"Is the user asking for NEW information on a specific topic (search), "
              f"or just reacting socially (like, emoji, 'cool', 'nice', 'why')? "
              f"Reply with exactly one word: 'social' or 'search'.")
    intent = generator.get_answer(llm, "", prompt, max_chars=20, temperature=0.1).strip().lower()
    return 'search' if 'search' in intent else 'social'

async def _check_relevance(llm, query: str, search_result: str, parent_ctx: str) -> bool:
    """
    Returns: True if search result is relevant to parent context
    """
    prompt = (f"Check semantic relevance.\n"
              f"Original Topic: {parent_ctx[:250]}\n"
              f"User Query: {query}\n"
              f"Search Result: {search_result[:250]}\n\n"
              f"Does the Search Result provide information relevant to the Original Topic or the User Query in this context? "
              f"Answer strictly 'yes' or 'no'.")
    answer = generator.get_answer(llm, "", prompt, max_chars=10, temperature=0.1).strip().lower()
    return 'yes' in answer

async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    parent_uri = task.get("parent_uri", "")
    if not parent_uri:
        logger.warning(f"[community] Missing parent_uri for {uri}")
        return
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return
    root_uri = chain.get("root_uri", parent_uri)
    if parent_uri != root_uri:
        logger.info(f"[community] Nested reply, skipping.")
        return
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("cid", "")
    if not parent_cid:
        logger.error(f"[community] Missing cid for {uri}")
        return
    
    parent_ctx = chain.get("root_text", "")
    clean_query = utils.clean_for_llm(user_text)
    
    intent = await _classify_intent(llm, user_text, parent_ctx)
    logger.info(f"[community] Intent: {intent} for query: {user_text[:30]}...")
    
    sig = build_content._get_signature("none", False)
    max_body = 300 - len(sig)
    reply = ""
    
    if intent == 'social':
        prompt = (f"User replied to a crypto post with: \"{user_text}\". "
                  f"Reply briefly (max {max_body} chars) in a friendly, natural tone. "
                  f"Acknowledge their vibe (positive/curious). No links, no markdown.")
        reply = generator.get_answer(llm, "", prompt, max_chars=max_body, temperature=0.7)
        
    else:
        kw = generator.extract_chainbase_keyword(llm, user_text)
        logger.info(f"[community] Extracted keyword: {kw}")
        search_data = ""
        if kw:
            search_data = await search.fetch_chainbase(kw)
        
        if search_data:
            is_relevant = await _check_relevance(llm, kw or clean_query, search_data, parent_ctx)
            logger.info(f"[community] Relevance check: {is_relevant}")
            
            if is_relevant:
                clean_search = utils.clean_for_llm(search_data)
                minimal_ctx = f"Q: {clean_query}\nA: {clean_search}"
                sig = build_content._get_signature("chainbase", True)
                max_body = 300 - len(sig)
                reply = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_body, temperature=0.5)
            else:
                prompt = (f"User asked about '{kw}', but the available info is not relevant to the current discussion context. "
                          f"Reply naturally (max {max_body} chars). Be friendly, concise. "
                          f"Mention that this topic might be trending elsewhere but isn't connected to the current thread. "
                          f"NEVER use 'I'm sorry' or 'I didn't understand'. Start directly.")
                reply = generator.get_answer(llm, "", prompt, max_chars=max_body, temperature=0.5)
        else:
            prompt = (f"User asked about '{kw or clean_query}'. No current data found. "
                      f"Reply naturally in English (max {max_body} chars). Be friendly, concise. "
                      f"NEVER use phrases like 'I'm sorry', 'I didn't understand'. "
                      f"Just say the info isn't available right now and suggest rephrasing or DYOR. "
                      f"Start directly with the answer.")
            reply = generator.get_answer(llm, "", prompt, max_chars=max_body, temperature=0.5)

    reply = utils.truncate_response(reply, max_body)
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")
