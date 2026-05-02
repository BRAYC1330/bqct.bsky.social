import httpx

def get_client():
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=5)
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
    return httpx.AsyncClient(limits=limits, timeout=timeout)
