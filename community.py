import logging
import config
import bsky
import generator
import search
import utils
import build_content
logger = logging.getLogger(__name__)
async def _classify_intent(llm, user_text: str, parent_ctx: str) -> str:
    prompt = (f"Analyze the user's reply in the context of the parent post.\n"
              f"Parent post context: {parent_ctx[:300]}\n"
              f"User reply: \"{user_text}\"\n\n"
              f"Determine if the user is requesting specific information requiring a search, "
              f"or simply expressing a social reaction or conversational remark. "
              f"Reply with exactly one word: 'search' or 'social'.")
    intent = generator.get_answer(llm, "", prompt, max_chars=20, temperature=0.1).strip().lower()
    return 'search' if 'search' in intent else 'social'
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
        prompt = (f"User replied to a post with: \"{user_text}\". "
                  f"Reply briefly (max {max_body} chars) in a friendly, natural tone. "
                  f"Acknowledge their vibe. "
                  f"IMPORTANT: This is a final reply. Do NOT ask questions or prompt further discussion. "
                  f"Give a short, warm acknowledgment. No links, no markdown, no hashtags.")
        reply = generator.get_answer(llm, "", prompt, max_chars=max_body, temperature=0.7)
    else:
        kw = generator.extract_chainbase_keyword(llm, user_text)
        logger.info(f"[community] Extracted keyword: {kw}")
        search_data = ""
        if kw:
            search_data = await search.fetch_chainbase(kw)
        sig = build_content._get_signature("chainbase", bool(search_data))
        max_body = 300 - len(sig)
        if search_data:
            prompt = (f"Search results for '{kw or clean_query}':\n{search_data[:1500]}\n\n"
                      f"Discussion context: {parent_ctx[:300]}\n"
                      f"User query: {clean_query}\n\n"
                      f"Answer the user's query using ONLY information that aligns with both the search results and the discussion context. "
                      f"Ignore unrelated data. Synthesize a concise, factual response. "
                      f"Max {max_body} chars. Start directly.")
            reply = generator.get_answer(llm, "", prompt, max_chars=max_body, temperature=0.4)
        else:
            topic_ref = kw if kw else clean_query[:50]
            if parent_ctx and topic_ref and topic_ref.lower() in parent_ctx.lower():
                ctx = f"[POST CONTEXT]\n{parent_ctx[:500]}\n\n[USER ASKED]\n{clean_query}"
                prompt = f"Based ONLY on the post context, briefly address '{topic_ref}'. Max {max_body} chars. Concise."
                reply = generator.get_answer(llm, ctx, prompt, max_chars=max_body, temperature=0.3)
                sig = build_content._get_signature("none", False)
            else:
                prompt = (f"User asked about '{topic_ref}'. No data found. "
                          f"Reply naturally (max {max_body} chars). Suggest rephrasing or independent research. "
                          f"NEVER use apologies. Start directly.")
                reply = generator.get_answer(llm, "", prompt, max_chars=max_body, temperature=0.5)
    reply = utils.truncate_response(reply, max_body)
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")