import logging
import re
import config
import bsky
import generator
import search
import utils
import build_content

logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri, user_text = task["uri"], task["text"]
    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    search_data, source = "", ""

    if do_search:
        clean_text = re.sub(r'(!t|!c)', '', user_text, flags=re.I).strip()
        if "!c" in user_text.lower():
            kw = generator.extract_chainbase_keyword(llm, clean_text)
            if kw: search_data, source = await search.fetch_chainbase(kw), "chainbase"
        else:
            q, t = generator.extract_search_intent(llm, "", clean_text)
            if q: search_data, source = await search.fetch_tavily(q, t), "tavily"

    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain or not chain.get("cid"): return

    root_uri, root_cid = chain.get("root_uri", uri), chain["root_cid"]
    thread_ctx = await utils._format_thread_for_llm(chain, config.OWNER_DID, config.BOT_DID, client)
    if search_data: search_data = utils.clean_for_llm(search_data)

    reply = await build_content.build_reply(llm, thread_ctx, user_text, search_data, source, max_total=300)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, chain["cid"])