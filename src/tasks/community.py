import logging
from src.state import settings as config
from src.clients import bsky, chainbase
from src.llm import inference as llm_infer
from src.content import builder, sanitizer, validator

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
    kw = llm_infer.extract_chainbase_keyword(llm, user_text)
    search_data = ""
    source = ""
    if kw:
        search_data = await chainbase.fetch_narrative(kw)
        source = "chainbase"
    if not search_
        reply = builder.get_no_data_response(kw or "query")
        await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
        return
    clean_query = sanitizer.clean(user_text)
    clean_search = sanitizer.clean(search_data)
    minimal_ctx = f"Q: {clean_query}\nA: {clean_search}"
    sig = builder._get_signature(source, True)
    max_body = 300 - len(sig)
    reply = llm_infer.get_answer(llm, minimal_ctx, clean_query, max_chars=max_body, temperature=0.5)
    reply = validator.enforce_limit(reply, max_body)
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
