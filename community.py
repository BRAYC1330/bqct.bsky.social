import logging
import config
import bsky
import generator
import search
import utils
import build_content
logger = logging.getLogger(__name__)
async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    parent_uri = task.get("parent_uri", "")
    if not parent_uri: return
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return
    root_uri = chain.get("root_uri", parent_uri)
    if parent_uri != root_uri: return
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("cid", "")
    if not parent_cid: return
    parent_ctx = chain.get("root_text", "")
    clean_query = utils.clean_for_llm(user_text)
    ext_prompt = (f"User query: '{clean_query}'\n"
                  f"Post context: '{parent_ctx[:300]}'\n\n"
                  f"Extract EXACTLY ONE single word from the post context that directly relates to the user query. "
                  f"If the input is purely a social reaction (emoji, short praise, thanks), reply 'SOCIAL'. "
                  f"Otherwise, reply with ONLY the single word.")
    kw = generator.get_answer(llm, "", ext_prompt, max_chars=20, temperature=0.1).strip().strip("'\"")
    has_data = False
    sig = ""
    max_body = 300
    if kw.upper() == "SOCIAL":
        sig = build_content._get_signature("none", False)
        max_body = 300 - len(sig)
        reply_prompt = (f"User reacted: '{user_text}' on a crypto post. "
                        f"Reply briefly, warmly, and close the conversation. "
                        f"NO questions. NO hashtags. NO markdown. Max {max_body} chars.")
    else:
        search_data = await search.fetch_chainbase(kw) if kw else ""
        has_data = bool(search_data) and kw.lower() in search_data.lower()
        sig = build_content._get_signature("chainbase", has_data)
        max_body = 300 - len(sig)
        if has_data:
            reply_prompt = (f"Search data for '{kw}':\n{search_data[:1500]}\n\n"
                            f"Post context: {parent_ctx[:300]}\n"
                            f"User query: {clean_query}\n\n"
                            f"Answer concisely using ONLY the provided data and context. "
                            f"Max {max_body} chars. Start directly.")
        else:
            reply_prompt = (f"No matching data found for '{kw}'. "
                            f"Reply briefly and naturally. NO questions. NO apologies. NO hashtags. "
                            f"Suggest rephrasing or checking back later. Max {max_body} chars. Start directly.")
    reply = generator.get_answer(llm, "", reply_prompt, max_chars=max_body, temperature=0.3)
    reply = reply.replace('#', '').strip()
    reply = utils.truncate_response(reply, max_body)
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Keyword: {kw} | Match: {has_data} | Replied to {uri[:40]}...")