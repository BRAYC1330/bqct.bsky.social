import os
import json
from typing import Dict, Any

def load_state() -> Dict[str, Any]:
    raw = os.getenv("LAST_PROCESSED", "{}").strip()
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}

def save_state(state: Dict[str, Any]) -> None:
    out_path = os.getenv("GITHUB_OUTPUT")
    if out_path:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(f"state_json={json.dumps(state, ensure_ascii=False)}\n")

def write_output(key: str, value: str) -> None:
    out_path = os.getenv("GITHUB_OUTPUT")
    if out_path:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")
