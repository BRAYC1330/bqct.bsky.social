import config
import utils
import generator
import logging
logger = logging.getLogger(__name__)
SIG_DIGEST = "\n\nQwen | Chainbase TOPS " + config.SIGNATURE_ICONS
SIG_TAVILY = "\n\nQwen | Tavily"
SIG_CHAINBASE = "\n\nQwen | Chainbase"
SIG_DEFAULT = "\n\nQwen"
def _get_signature(source: str, has_search: bool) -> str:
    if source == "tavily": return SIG_TAVILY
    if source == "chainbase": return SIG_CHAINBASE
    if has_search: return SIG_CHAINBASE
    return SIG_DEFAULT
def get_no_data_response(keyword: str) -> str:
    body = f'No data found for "{keyword}". Try rephrasing your query in a new comment or DYOR.'
    return f"{body}\n\nQwen"
async def build_reply(llm, thread_ctx: str, query: str, search_data: str = "", source: str = "", max_total: int = 300) -> str:
    sig = _get_signature(source, bool(search_data))
    max_body = max_total - len(sig)
    if search_data:
        ctx = f"[SEARCH]\n{search_data}\n{thread_ctx}"
    else:
        ctx = thread_ctx
    reply = generator.get_answer(llm, ctx, query, max_chars=max_body, temperature=0.5)
    if utils.count_graphemes(reply) > max_body:
        truncated = reply[:max_body]
        last_dot = truncated.rfind(".")
        reply = truncated[:last_dot+1] if last_dot != -1 else truncated.rstrip() + "."
    return reply.strip() + sig
async def build_digest(llm, trends, task_type: str, max_total: int = 300) -> str | None:
    if not trends: return None
    sig = SIG_DIGEST
    max_body = max_total - len(sig)
    emojis = config.TREND_EMOJIS
    if task_type == "digest_mini":
        header = "TOP CRYPTO TRENDS:\n\n"
        lines = []
        for item in trends[:6]:
            kw = item.get("keyword", "?")
            sc = item.get("score")
            st = item.get("rank_status", "same")
            e = emojis.get(st.lower(), "")
            lines.append(f"{e} {kw} 📊 {sc}")
            if len("\n".join(lines)) + len(header) > max_body:
                lines.pop()