import logging
import os
import sys
import re
from datetime import datetime, timezone

class SecretFilter(logging.Filter):
    PATTERNS = [
        r'Bearer\s+[A-Za-z0-9\-_\.]+',
        r'(?i)(?:api[_\-]?key|token|secret|password|pat|credential)\s*[:=]\s*["\']?[A-Za-z0-9\-_\.]{8,}',
        r'did:[^\s"\',}]+',
        r'at://[^\s"]+',
        r'(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}'
    ]
    def filter(self, record):
        if isinstance(record.msg, str):
            for p in self.PATTERNS:
                record.msg = re.sub(p, '[REDACTED]', record.msg, flags=re.I)
        return True

def setup_logging():
    level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
    level = getattr(logging, level_str, logging.INFO)
    fmt = '%(asctime)s [%(levelname)s] %(message)s'
    datefmt = '%Y-%m-%dT%H:%M:%S'
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    handler.addFilter(SecretFilter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)