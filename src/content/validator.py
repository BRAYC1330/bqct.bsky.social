import config

def count_graphemes(text):
    return len(text) if text else 0

def count_tokens(text, llm=None):
    if not text: return 0
    if llm:
        try: return len(llm.tokenize(text.encode("utf-8")))
        except Exception: pass
    return max(1, int(len(text) * config.TOKEN_TO_CHAR_RATIO))

def enforce_limit(text, max_total):
    if count_graphemes(text) <= max_total: return text
    truncated = text[:max_total]
    last_dot = truncated.rfind(".")
    if last_dot != -1: return truncated[:last_dot+1]
    return truncated.rstrip() + "."
