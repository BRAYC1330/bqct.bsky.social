import os
import logging
import config
import bsky
import generator
import state
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    parent_uri = task.get("parent_uri", "")
    if not parent_uri:
        return
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return

    root_uri = chain["root_uri"]
    root_cid = chain["root_cid"]
    parent_cid = chain.get("parent_cid", "")
    root_thread = f"Root: {chain['root_text'][:200]}"

    memory = state.load_digest_context()
    final_ctx = state.merge_contexts(memory, root_thread, "", user_text)

    reply = generator.get_answer(llm, final_ctx, user_text, "", max_chars=280, temperature=0.7)
    if len(reply) > 293:
        reply = generator.get_answer(llm, final_ctx, user_text, "", max_chars=260, temperature=0.7)
    if len(reply) > 293:
        return

    reply = reply.strip() + "\n\nQwen"
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")