import os
import logging
import re
import config
import bsky
import generator
import state
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
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
    thread_context_parts = []
    for post in chain.get("chain", []):
        rec = post.get("record", {})
        author = post.get("author", {})
        p_text = rec.get("text", "")
        embed = rec.get("embed")
        embed_text, alts = bsky._extract_embed_full(embed) if embed else ("", [])
        if embed_text:
            p_text += f" {embed_text}"
        if alts:
            p_text += " " + " ".join(alts)
        urls = URL_PATTERN.findall(p_text)
        for url in urls:
            clean = await bsky._extract_clean_url_content(url)
            if clean:
                p_text += f" [Linked: {clean}]"
        thread_context_parts.append(f"@{author.get('handle')}: {p_text}")
    full_thread_context = "\n".join(thread_context_parts)
    final_ctx = state.merge_contexts(memory, full_thread_context, "", user_text)
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