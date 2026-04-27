import os
import logging
import config
import bsky
import generator
import state
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)
async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    parent_uri = task.get("parent_uri", "")
    if not parent_uri:
        logger.warning(f"[community] Missing parent_uri for {uri}")
        return
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
    root_uri = chain.get("root_uri", parent_uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    memory, _ = state.load_context(root_uri)
    thread_context = utils._clean_thread_for_llm(chain, config.OWNER_DID, max_recent=12)
    final_ctx = state.merge_contexts(memory, thread_context, "", user_text)
    reply = generator.get_answer(llm, final_ctx, user_text, "", max_chars=280, temperature=0.7)
    if utils.count_graphemes(reply) > 293:
        logger.warning(f"[community] Reply too long ({utils.count_graphemes(reply)}), regenerating...")
        reply = generator.get_answer(llm, final_ctx, user_text, "", max_chars=260, temperature=0.7)
    if utils.count_graphemes(reply) > 293:
        logger.error(f"[community] Reply still too long, skipping post")
        return
    reply = reply.strip() + "\nQwen"
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    if root_uri != os.environ.get("ACTIVE_DIGEST_URI", "").strip():
        state.save_context(root_uri, generator.update_summary(llm, memory, user_text, reply))
    logger.info(f"[community] Replied to {uri[:40]}...")