import logging
import re
import generator
import search
import utils
import reply
logger = logging.getLogger(__name__)
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

async def process(client, llm, task):
    user_text = task["text"]
    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    search_data, link_content = "", ""
    suffix = ""

    if do_search:
        clean = user_text.replace("!t", "").replace("!c", "").strip()
        if "!t" in user_text.lower():
            q, t = generator.extract_tavily_intent(llm, clean)
            if q:
                search_data = await search.fetch_tavily(q, t)
            suffix = "\n\nQwen"
        elif "!c" in user_text.lower():
            kw = generator.extract_chainbase_keyword(llm, clean)
            logger.info(f"[owner] KEYWORD_EXTRACTED: {kw}")
            if kw:
                search_data = await search.fetch_chainbase(kw)
            suffix = "\n\nQwen | Chainbase" if search_data else "\n\nQwen"

    urls = URL_PATTERN.findall(user_text)
    if urls:
        import link_extractor
        ext = link_extractor.LinkExtractor()
        try:
            contents = [f"[LINK:{u}]\n{c}" for u in urls[:2] if (c := await ext.extract(u))]
            link_content = "\n\n".join(contents)
        finally:
            await ext.close()

    await reply.process_reply(client, llm, task, max_chars=240, suffix=suffix, temperature=0.7, search_data=search_data, link_content=link_content)