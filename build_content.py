import config
import utils
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

async def build_digest(llm, trends, task_type: str, max_total: int = 300) -> str | None:
    if not trends: return None
    sig = SIG_DIGEST
    emojis = config.TREND_EMOJIS
    if task_type == "digest_mini":
        header = "TOP CRYPTO TRENDS:\n\n"
        lines = []
        for item in trends[:6]:
            kw, sc, st = item.get("keyword","?"), item.get("score"), item.get("rank_status","same")
            e = emojis.get(st.lower(), "")
            lines.append(f"{e} {kw} 📊 {sc}")
            if len("\n".join(lines)) + len(header) > max_total - len(sig):
                lines.pop(); break
        if not lines: return None
        body = f"{header}" + "\n".join(lines)
    else:
        item = trends[0]
        kw, sc, st, sm = item.get("keyword","?"), item.get("score"), item.get("rank_status","same"), item.get("summary","")
        e = emojis.get(st.lower(), "")
        title = f"{e + ' ' if e else ''}{kw} 📊 {sc}:"
        header = "TOP CRYPTO TREND:\n\n"
        fixed_len = len(header) + len(title) + 1 + len(sig)
        max_desc = max_total - fixed_len
        if max_desc < 30: return None
        from generator import load_prompt
        prompt_text = load_prompt("digest_refine", keyword=kw, summary=sm)
        output = llm(prompt_text, max_tokens=150, temperature=0.5)
        desc = output.get("choices", [{}])[0].get("text", "").strip()
        if utils.count_graphemes(desc) > max_desc:
            t = desc[:max_desc]; last = t.rfind(".")
            desc = t[:last+1] if last != -1 else t.rstrip() + "."
        body = f"{header}{title} {desc}"
    final = body + sig
    return final if utils.count_graphemes(final) <= max_total else None