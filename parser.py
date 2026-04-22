import logging
from typing import List, Dict, Optional, TypedDict
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)
class PostNode(TypedDict):
    uri: str
    cid: str
    handle: str
    text: str
    is_root: bool
THREAD_CACHE: Dict[str, List[PostNode]] = {}
async def parse_thread(thread_data: dict, root_uri: str = "", client=None):
    logger.debug(f"[parse_thread] Parsing thread data")
    nodes = utils.flatten_thread(thread_data.get("thread", {}))
    logger.debug(f"[parse_thread] Extracted {len(nodes)} nodes")
    return nodes
async def parse_digest_thread(thread_ Dict) -> Dict:
    logger.debug(f"[parse_digest_thread] Parsing thread with {len(thread_data.get('thread', {}))} nodes")
    nodes = utils.flatten_thread(thread_data.get("thread", {}))
    root = next((n for n in nodes if n.get("is_root")), {"uri": "", "cid": "", "text": ""})
    comments = [n for n in nodes if not n.get("is_root") and n.get("uri") != root["uri"]]
    logger.debug(f"[parse_digest_thread] Root: {root['uri'][:30]}..., comments: {len(comments)}")
    return {"uri": root["uri"], "cid": root["cid"], "text": root["text"], "comments": comments}
