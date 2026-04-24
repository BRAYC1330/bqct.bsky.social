import logging
import time
import asyncio
from collections import OrderedDict
from typing import Optional, Dict
from urllib.parse import urlparse
import httpx
from trafilatura import extract as trafilatura_extract
import config
import utils
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

class LinkExtractor:
    def __init__(self):
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self._max_cache_size = 100
        self._ttl = config.LINK_CACHE_TTL
        self._allowed_domains = config.ALLOWED_LINK_DOMAINS
        self._max_content = config.MAX_LINK_CONTENT_SIZE
        self._lock = asyncio.Lock()
        logger.debug("[LinkExtractor] Initialized")

    def _evict_if_needed(self):
        while len(self._cache) > self._max_cache_size:
            self._cache.popitem(last=False)

    async def extract(self, url: str) -> Optional[str]:
        logger.debug(f"[LinkExtractor.extract] Fetching {url}")
        async with self._lock:
            if url in self._cache:
                content, timestamp = self._cache[url]
                if time.time() - timestamp < self._ttl:
                    self._cache.move_to_end(url)
                    logger.debug(f"[LinkExtractor.extract] Cache hit")
                    return content
        
        try:
            parsed = urlparse(url)
            if parsed.netloc and parsed.netloc not in self._allowed_domains:
                logger.debug(f"[LinkExtractor.extract] Domain not allowed: {parsed.netloc}")
                async with self._lock:
                    self._cache[url] = (None, time.time())
                    self._evict_if_needed()
                return None
            
            async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=config.CONNECT_TIMEOUT)) as client:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=config.REQUEST_TIMEOUT)
                if r.status_code == 200:
                    content = trafilatura_extract(r.text, include_tables=False, include_comments=False, output_format="txt")
                    result = utils.sanitize_for_prompt(content[:self._max_content]) if content else None
                    async with self._lock:
                        self._cache[url] = (result, time.time())
                        self._cache.move_to_end(url)
                        self._evict_if_needed()
                    logger.debug(f"[LinkExtractor.extract] Extracted {len(result) if result else 0} chars")
                    return result
                async with self._lock:
                    self._cache[url] = (None, time.time())
                    self._evict_if_needed()
                logger.warning(f"[LinkExtractor.extract] HTTP {r.status_code}")
                return None
        except Exception as e:
            logger.warning(f"[LinkExtractor.extract] Failed: {e}")
            async with self._lock:
                self._cache[url] = (None, time.time())
                self._evict_if_needed()
            return None

    def clear(self):
        self._cache.clear()
        logger.debug("[LinkExtractor.clear] Cache cleared")
