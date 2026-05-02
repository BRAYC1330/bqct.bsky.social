import logging
import re
from src.state import settings as config
from src.clients import bsky, tavily, chainbase
from src.llm import inference as llm_infer
from src.content import builder, sanitizer

logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    search_data = ""
    source = ""
    if do_search:
        clean_text = re.sub(r'(!t|!c)', '', user_text, flags=re.I).strip()
        if "!c" in user_text.lower():
            kw = llm_infer.extract_chainbase_keyword(llm, clean_text)
            if kw:
                search_data = await chainbase.fetch_narrative(kw)
                source = "chainbase"
        else:
            q, t = llm_infer.extract_search_intent(llm, "", clean_text)
            if q:
                search_data = await tavily.fetch(q, t)
                source = "tavily"
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_uri = uri
    parent_cid = chain.get("cid", "")
    if not parent_cid: return
    thread_ctx = await sanitizer.format_thread(chain, config.OWNER_DID, config.BOT_DID, client)
    if search_ search_data = sanitizer.clean(search_data)
    reply = await builder.build_reply(llm, thread_ctx, user_text, search_data, source, max_total=300)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, parent_uri, parent_cid)
