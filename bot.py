import os
import json
import asyncio
import logging
import httpx
import config
import state
import search
import generator
import bsky
import timers
import parser
import community
from link_extractor import LinkExtractor
from utils import flatten_thread, extract_embed_full, with_retry, sanitize_for_prompt
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process_item(client, item, llm):
    uri = item["uri"]
    user_text = item["text"]
    do_search = item.get("has_search", False)
    search_type = item.get("search_type", "tavily")
    chain = await with_retry(lambda: bsky.fetch_thread_chain(client, uri))
    if not chain:
        return

    nodes = []
    for idx, post in enumerate(chain["chain"]):
        rec = post.get("record", {})
        author = post.get("author", {})
        txt = rec.get("text", "")
        embed_text, alts = extract_embed_full(rec.get("embed")) if rec.get("embed") else ("", [])
        link_hints = []
        for url in [u for u in txt.split() if u.startswith("http")]:
            clean = await LinkExtractor().extract(url)
            if clean:
                link_hints.append(f"[Link: {clean[:150]}]")
        nodes.append({"handle": author.get("handle"), "text": txt, "alts": alts, "links": link_hints, "is_root": idx == 0})
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-THREAD-PARSED ===\n{json.dumps(nodes, ensure_ascii=False, indent=2)}\n=== END ===")

    memory = state.load_context(chain["root_uri"])
    search_data = ""
    if do_search:
        params = generator.extract_search_params(llm, "", user_text)
        provider = search.SEARCH_PROVIDERS.get(search_type)
        if provider:
            raw = await with_retry(lambda: provider["func"](params.get("query", ""), **{k: v for k, v in params.items() if k in provider["supports"] and v}))
            if search.is_search_result_valid(raw, search_type):
                search_data = raw[:3000]

    root_thread = "\n".join([f"@{n['handle']}: {n['text']} {' '.join(n['links'])}" for n in nodes if n['is_root'] or n.get('text')])
    final_ctx = state.merge_contexts(memory, root_thread, search_data, user_text)

    reply = generator.get_answer(llm, final_ctx, user_text, search_data, config.RESPONSE_MAX_CHARS)
    await with_retry(lambda: bsky.post_reply(client, config.BOT_DID, reply, chain["root_uri"], chain["root_cid"], uri, chain["parent_cid"]))
    state.save_context(chain["root_uri"], generator.update_summary(llm, memory, user_text, reply))

async def main():
    logger.info("[main] === START ===")
    async with bsky.get_client() as client:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        mini_due = timers.check_mini_timer()
        full_due = timers.check_full_timer()
        has_work = os.path.exists("work_data.json")

        llm = None
        if mini_due or full_due or has_work:
            llm = generator.get_model()

        if llm:
            active = os.getenv("ACTIVE_DIGEST_URI", "")
            if active and active not in ("{}", "null", ""):
                rec = await bsky.get_record(client, active)
                if rec:
                    await community.process_digest_community(client, llm, active, rec["value"].get("text", ""))
            if mini_due or full_due:
                from news import post_if_due
                await post_if_due(client, llm)

        if has_work and llm:
            with open("work_data.json") as f:
                data = json.load(f)
            await asyncio.gather(*[process_item(client, i, llm) for i in data.get("items", [])])

    logger.info("[main] === DONE ===")

if __name__ == "__main__":
    asyncio.run(main())
