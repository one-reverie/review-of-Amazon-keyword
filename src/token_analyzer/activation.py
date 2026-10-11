from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

from .settings import protect_secret, unprotect_secret


PRODUCT_ID = "token-analyzer-windows-v1"
_ACTIVATION_VERSION = 2
_ACTIVATION_CODE_DIGEST = bytes.fromhex(
    "5cb42d1d835b99b5b67f98ca48fbfbfa932e70a4c4cb76e285c5e28800eabc74"
)


def verify_activation_code(activation_code: str) -> bool:
    normalized = str(activation_code).strip()
    if not normalized:
        return False
    digest = hashlib.sha256(f"{PRODUCT_ID}|{normalized}".encode("utf-8")).digest()
    return hmac.compare_digest(digest, _ACTIVATION_CODE_DIGEST)


def default_activation_path() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "TokenAnalyzer" / "activation.json"


class ActivationStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_activation_path()

    def is_activated(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != _ACTIVATION_VERSION:
                return False
            encrypted = payload.get("credential_encrypted")
            if not isinstance(encrypted, str) or not encrypted:
                return False
            credential = json.loads(unprotect_secret(encrypted))
            return bool(
                isinstance(credential, dict)
                and credential.get("product_id") == PRODUCT_ID
                and credential.get("activated") is True
            )
        except (OSError, RuntimeError, TypeError, ValueError, UnicodeError, RecursionError):
            return False

    def activate(self, activation_code: str) -> bool:
        if not verify_activation_code(activation_code):
            return False
        try:
            credential = json.dumps(
                {"product_id": PRODUCT_ID, "activated": True},
                ensure_ascii=True,
                separators=(",", ":"),
            )
            encrypted = protect_secret(credential)
            if not encrypted:
                return False
            stored_payload = json.dumps(
                {"version": _ACTIVATION_VERSION, "credential_encrypted": encrypted},
                ensure_ascii=True,
                indent=2,
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(stored_payload, encoding="utf-8")
            os.replace(temporary, self.path)
            return True
        except (OSError, RuntimeError, TypeError, ValueError):
            return False
