import logging
import config
import bsky
import generator
import search
import utils
import build_content

logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri, user_text = task["uri"], task["text"]
    parent_uri = task.get("parent_uri", "")
    if not parent_uri: return

    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain or chain.get("root_uri", parent_uri) != parent_uri or not chain.get("cid"): return

    root_uri, root_cid = chain["root_uri"], chain["root_cid"]
    parent_cid = chain["cid"]

    kw = generator.extract_chainbase_keyword(llm, user_text)
    search_data = await search.fetch_chainbase(kw) if kw else ""
    reply = await build_content.build_reply(llm, "", user_text, search_data, source="chainbase" if search_data else "", max_total=300)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)