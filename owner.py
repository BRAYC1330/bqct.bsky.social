import logging
import re
import generator
import search
import utils
import link_extractor
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

async def process(client, llm, task):
    user_text = task["text"]
    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    search_query, time_range = "", ""
    search_data = ""
    link_content = ""
    
    if do_search:
        clean_text = user_text.replace("!t", "").replace("!c", "").strip()
        search_query, time_range = generator.extract_search_intent(llm, "", clean_text)
        if search_query:
            if "!c" in user_text.lower():
                search_data = await search.fetch_chainbase(search_query)
            else:
                search_data = await search.fetch_tavily(search_query, time_range)
    
    urls = URL_PATTERN.findall(user_text)
    if urls:
        extractor = link_extractor.LinkExtractor()
        contents = []
        for url in urls[:2]:
            content = await extractor.extract(url)
            if content:
                contents.append(f"[LINK:{url}]\n{content}")
        link_content = "\n\n".join(contents)
    
    await utils.process_reply(client, llm, task, max_chars=280, suffix="", temperature=0.7, search_data=search_data, link_content=link_content)