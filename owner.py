import os
import logging
import config
import bsky
import generator
import memory
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    parent_uri = task.get("parent_uri", "")
    if not parent_uri:
        logger.warning(f"[owner] No parent_uri for {uri[:40]}, skipping")
        return
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        logger.error(f"[owner] Failed to fetch thread chain for {uri[:40]}")
        return
    root_uri = chain["root_uri"]
    root_cid = chain["root_cid"]
    target_uri = chain.get("target_uri", uri)
    target_cid = chain.get("target_cid", "")
    parent_cid = chain.get("parent_cid", "")
    if not target_cid:
        logger.error(f"[owner] Missing target_cid for {uri[:40]}, skipping")
        return
    logger.info(f"[owner] Reply targeting: target={target_uri[:40]} | parent={parent_uri[:40]}")
    root_thread = f"Root: {chain['root_text'][:200]}"
    mem = memory.merge_contexts("", root_thread, "", user_text)
    final_ctx = memory.merge_contexts(mem, root_thread, "", user_text)
    reply = generator.get_answer(llm, final_ctx, user_text, "", max_chars=290, temperature=0.7).strip() + "\nQwen"
    if len(reply) > 295:
        reply = generator.get_answer(llm, final_ctx, user_text, "", max_chars=260, temperature=0.7).strip() + "\nQwen"
    if len(reply) > 295:
        logger.warning(f"[owner] Reply too long: {len(reply)} chars, skipping")
        return
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, target_uri, target_cid)
    logger.info(f"[owner] Reply sent successfully to {target_uri[:40]}")
