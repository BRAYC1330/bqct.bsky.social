import base64
import httpx
from nacl import encoding, public

def _get_headers(pat: str) -> dict:
    return {"Authorization": f"token {pat}"}

def _encrypt_secret(pk: str, secret_value: str) -> str:
    pk_obj = public.PublicKey(pk.encode("utf-8"), encoding.Base64Encoder())
    return base64.b64encode(public.SealedBox(pk_obj).encrypt(secret_value.encode("utf-8"))).decode("utf-8")

async def read_secret(repo: str, pat: str, secret_name: str, max_retries: int = 3) -> str:
    url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
    for i in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url, headers=_get_headers(pat))
                if r.status_code == 200:
                    return r.json().get("value", "")
                if r.status_code in (429, 500, 502):
                    continue
        except Exception:
            if i < max_retries - 1:
                continue
    return ""

async def write_secret(repo: str, pat: str, secret_name: str, value: str, max_retries: int = 3) -> bool:
    key_url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
    put_url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
    for i in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                key_resp = await client.get(key_url, headers=_get_headers(pat))
                key_data = key_resp.json()
                enc = _encrypt_secret(key_data["key"], value)
                r = await client.put(put_url, headers=_get_headers(pat), json={"encrypted_value": enc, "key_id": key_data["key_id"]})
                if r.status_code in (201, 204):
                    return True
                if r.status_code in (429, 500, 502):
                    continue
        except Exception:
            if i < max_retries - 1:
                continue
    return False
