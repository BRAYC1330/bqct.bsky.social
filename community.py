import logging
import config
import generator
import bsky

logger = logging.getLogger(__name__)

async def process_digest_community(client, llm, digest_uri: str, digest_text: str):
    try:
        replies = await bsky.get_replies(client, digest_uri)
        if not replies:
            logger.info("[COMMUNITY] Digest: no replies. Skipping.")
            return

        external = [r for r in replies if r.get("author", {}).get("did") != config.BOT_DID]
        if not external:
            logger.info("[COMMUNITY] Digest: no external replies. Skipping.")
            return

        target = external[0]
        comment_text = target.get("record", {}).get("text", "") or target.get("text", "")
        logger.info(f"[COMMUNITY] Digest replying to: {target.get('author', {}).get('handle')}")

        reply = generator.get_reply(
            llm=llm,
            memory="",
            root_thread="",
            search_data="",
            query=comment_text
        )

        await bsky.reply_to(client, digest_uri, target.get("uri"), reply)
        logger.info("[COMMUNITY] Digest reply posted. Context and memory saving skipped.")

    except Exception as e:
        logger.error(f"[COMMUNITY] process_digest_community failed: {e}")