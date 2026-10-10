"""Tuya Cloud signing and device access; no local keys or hardware process."""
import hashlib
import hmac
import json
import time
from urllib.parse import quote

from .service import ServiceError

REGIONS = {
    "eu": "https://openapi.tuyaeu.com",
    "us": "https://openapi.tuyaus.com",
    "cn": "https://openapi.tuyacn.com",
    "in": "https://openapi.tuyain.com",
    "eu_west": "https://openapi-weaz.tuyaeu.com",
    "us_east": "https://openapi-ueaz.tuyaus.com",
}


def signed_headers(access_id, secret, method, path, body, token="", timestamp=None):
    timestamp = timestamp or str(int(time.time() * 1000))
    string_to_sign = method.upper() + "\n" + hashlib.sha256(body).hexdigest() + "\n\n" + path
    signature = hmac.new(secret.encode(), (access_id + token + timestamp + string_to_sign).encode(), hashlib.sha256).hexdigest().upper()
    headers = {"client_id": access_id, "t": timestamp, "sign": signature, "sign_method": "HMAC-SHA256", "Content-Type": "application/json"}
    if token:
        headers["access_token"] = token
    return headers


class TuyaCloud:
    def __init__(self, client):
        self.client = client
        self.tokens = {}
        self.functions = {}

    async def raw(self, entry, method, path, data=None, token=""):
        import httpx
        body = b"" if data is None else json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
        headers = signed_headers(entry["access_id"], entry["secret"], method, path, body, token)
        try:
            response = await self.client.request(method, REGIONS[entry["region"]] + path, headers=headers, content=body)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            raise ServiceError(502, "tuya_unavailable", "Unable to reach Tuya Cloud") from None
        if not isinstance(payload, dict) or payload.get("success") is not True:
            code = str(payload.get("code", "unknown")) if isinstance(payload, dict) else "unknown"
            # Remote messages may contain account identifiers; expose only a known diagnostic.
            detail = "Tuya rejected the request (code " + code[:12] + "). Check credentials, data center, account linking and API permissions."
            raise ServiceError(502, "tuya_api_error", detail)
        if "result" not in payload:
            raise ServiceError(502, "tuya_invalid_response", "Tuya returned an invalid response")
        return payload["result"]

    async def request(self, entry, method, path, data=None):
        key = (entry["access_id"], entry["region"], hashlib.sha256(entry["secret"].encode()).hexdigest())
        token, expires = self.tokens.get(key, ("", 0))
        if time.monotonic() >= expires:
            result = await self.raw(entry, "GET", "/v1.0/token?grant_type=1")
            token = result["access_token"]
            self.tokens[key] = (token, time.monotonic() + max(1, result["expire_time"] - 60))
        try:
            return await self.raw(entry, method, path, data, token)
        except ServiceError:
            self.tokens.pop(key, None)
            raise

    async def devices(self, entry):
        inventory = await self.request(entry, "GET", "/v1.0/users/" + quote(entry["uid"], safe="") + "/devices")
        if not isinstance(inventory, list):
            raise ServiceError(502, "tuya_invalid_inventory", "Tuya returned an invalid inventory")
        devices = []
        for item in inventory:
            path = "/v1.0/devices/" + quote(item["id"], safe="")
            cache_key = (entry["access_id"], entry["region"], item["id"])
            functions, expires = self.functions.get(cache_key, (None, 0))
            if functions is None or time.monotonic() >= expires:
                try:
                    functions = await self.request(entry, "GET", path + "/specifications")
                except ServiceError:
                    functions = await self.request(entry, "GET", path + "/functions")
                self.functions[cache_key] = (functions, time.monotonic() + 600)
            devices.append(device_snapshot(item, functions))
        return devices

    async def command(self, entry, external_id, code, value, preceding=None):
        result = await self.request(entry, "POST", "/v1.0/devices/" + quote(external_id, safe="") + "/commands", {"commands": [*(preceding or []), {"code": code, "value": value}]})
        if result is not True:
            raise ServiceError(502, "tuya_command_rejected", "Tuya did not accept the device command")


def device_snapshot(item, functions):
    controls = []
    for function in functions.get("functions", []):
        if function["type"] not in {"Boolean", "Integer", "Enum", "Json"}:
            continue
        constraints = json.loads(function.get("values") or "{}")
        if function["type"] == "Integer":
            if not all(type(constraints.get(key)) is int for key in ("min", "max")) or constraints["max"] < constraints["min"] or constraints.get("step", 1) <= 0:
                continue
        if function["type"] == "Enum" and not isinstance(constraints.get("range"), list):
            continue
        if function["type"] == "Json":
            if not constraints and item.get("category") == "dj" and function["code"] in {"colour_data", "colour_data_v2"}:
                # Tuya's standard dj instruction set defines these HSV ranges.
                maximum = 1000 if function["code"] == "colour_data_v2" else 255
                constraints = {channel: {"min": 0, "max": 360 if channel == "h" else maximum, "step": 1} for channel in ("h", "s", "v")}
            # Color uses advertised ranges or the documented standard dj definition.
            if function["code"] not in {"colour_data", "colour_data_v2"} or not all(isinstance(constraints.get(channel), dict) and type(constraints[channel].get("min")) is int and type(constraints[channel].get("max")) is int and constraints[channel]["max"] >= constraints[channel]["min"] and constraints[channel].get("step", 1) > 0 for channel in ("h", "s", "v")):
                continue
        controls.append(dict(code=function["code"], name=str(function.get("name") or function["code"]), type=function["type"], constraints=constraints))
    status = {value["code"]: value["value"] for value in item.get("status", [])}
    status_specs = {}
    for specification in functions.get("status", []):
        try:
            values = json.loads(specification.get("values") or "{}")
            if isinstance(values, dict):
                status_specs[specification["code"]] = values
        except (TypeError, ValueError, KeyError):
            continue
    for control in controls:
        if control["type"] == "Json" and isinstance(status.get(control["code"]), str):
            try:
                status[control["code"]] = json.loads(status[control["code"]])
            except ValueError:
                pass
    return dict(external_id=item["id"], name=str(item.get("name") or item["id"])[:128], kind=str(item.get("category") or "device"), state=status, status_specs=status_specs, available=item.get("online") is True, controls=controls, product_name=str(item.get("product_name") or ""), updated_at=None)
