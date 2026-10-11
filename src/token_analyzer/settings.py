from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    base_url: str
    model: str
    api_key: str = ""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(value: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(value)
    blob = _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _windows_crypto_functions():
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    return crypt32, kernel32


def protect_secret(secret: str) -> str:
    if not secret:
        return ""
    if os.name != "nt":
        raise RuntimeError("API密钥安全保存仅支持Windows")
    input_blob, input_buffer = _blob_from_bytes(secret.encode("utf-8"))
    output_blob = _DataBlob()
    crypt32, kernel32 = _windows_crypto_functions()
    success = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(output_blob),
    )
    _ = input_buffer
    if not success:
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        kernel32.LocalFree(output_blob.pbData)


def unprotect_secret(value: str) -> str:
    if not value:
        return ""
    if os.name != "nt":
        raise RuntimeError("API密钥安全读取仅支持Windows")
    encrypted = base64.b64decode(value.encode("ascii"), validate=True)
    input_blob, input_buffer = _blob_from_bytes(encrypted)
    output_blob = _DataBlob()
    crypt32, kernel32 = _windows_crypto_functions()
    success = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(output_blob),
    )
    _ = input_buffer
    if not success:
        raise ctypes.WinError()
    try:
        decrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return decrypted.decode("utf-8")
    finally:
        kernel32.LocalFree(output_blob.pbData)


def default_settings_path() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "TokenAnalyzer" / "settings.json"


class ModelSettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_settings_path()

    def _read_payload(self) -> dict[str, object]:
        if not self.path.exists():
            return {"active_provider": "", "profiles": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"active_provider": "", "profiles": {}}
        if not isinstance(payload, dict) or not isinstance(payload.get("profiles", {}), dict):
            return {"active_provider": "", "profiles": {}}
        return payload

    def providers(self) -> list[str]:
        profiles = self._read_payload().get("profiles", {})
        return sorted(str(name) for name in profiles)

    def active_provider(self) -> str:
        return str(self._read_payload().get("active_provider", ""))

    def load(self, provider: str | None = None) -> ModelProfile | None:
        payload = self._read_payload()
        provider_name = (provider or str(payload.get("active_provider", ""))).strip()
        profiles = payload.get("profiles", {})
        if not provider_name or not isinstance(profiles, dict):
            return None
        raw = profiles.get(provider_name)
        if not isinstance(raw, dict):
            return None
        try:
            api_key = unprotect_secret(str(raw.get("api_key_encrypted", "")))
        except (ValueError, OSError, RuntimeError):
            api_key = ""
        return ModelProfile(
            provider=provider_name,
            base_url=str(raw.get("base_url", "")),
            model=str(raw.get("model", "")),
            api_key=api_key,
        )

    def save(self, profile: ModelProfile) -> None:
        provider = profile.provider.strip()
        if not provider:
            raise ValueError("请填写服务商名称")
        payload = self._read_payload()
        profiles = payload.setdefault("profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
            payload["profiles"] = profiles
        stored = asdict(profile)
        stored.pop("api_key", None)
        stored["api_key_encrypted"] = protect_secret(profile.api_key)
        profiles[provider] = stored
        payload["active_provider"] = provider
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def delete(self, provider: str) -> None:
        payload = self._read_payload()
        profiles = payload.get("profiles", {})
        if isinstance(profiles, dict):
            profiles.pop(provider, None)
        if payload.get("active_provider") == provider:
            payload["active_provider"] = next(iter(profiles), "") if isinstance(profiles, dict) else ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def load_custom_weights(self) -> dict[str, float]:
        defaults = {
            "orders": 0.35,
            "clicks": 0.25,
            "impressions": 0.10,
            "cvr": 0.15,
            "ctr": 0.10,
            "frequency": 0.05,
        }
        raw = self._read_payload().get("custom_weights")
        if not isinstance(raw, dict) or set(raw) != set(defaults):
            return defaults
        try:
            weights = {key: float(raw[key]) for key in defaults}
        except (TypeError, ValueError):
            return defaults
        if any(value < 0 for value in weights.values()) or abs(sum(weights.values()) - 1.0) > 0.0001:
            return defaults
        return weights

    def save_custom_weights(self, weights: dict[str, float]) -> None:
        expected = {"orders", "clicks", "impressions", "cvr", "ctr", "frequency"}
        if set(weights) != expected or any(value < 0 for value in weights.values()):
            raise ValueError("自定义权重不完整")
        if abs(sum(weights.values()) - 1.0) > 0.0001:
            raise ValueError("自定义权重合计必须为100%")
        payload = self._read_payload()
        payload["custom_weights"] = weights
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
