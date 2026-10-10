"""Account authorization and device sharing through Tuya's official SDK."""
import asyncio
import base64
import io
import json
import time
from urllib.parse import quote, urlsplit

import httpx
import qrcode
from qrcode.image.svg import SvgPathImage
from tuya_sharing.customerapi import CustomerApi, CustomerTokenInfo
from tuya_sharing.customerlogging import logger as sdk_logger

from .service import ServiceError
from .tuya import device_snapshot

# Public application identity published by Tuya's Smart Life integration.
# https://github.com/tuya/tuya-smart-life/blob/main/custom_components/smartlife/const.py
CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
LOGIN_URL = "https://apigw.iotbing.com/v1.0/m/life/home-assistant/qrcode/tokens"
# SDK diagnostics include decrypted credentials and remote messages.
sdk_logger.disabled = True


def account_credentials(result):
    """Validate vendor credentials before persisting or contacting an endpoint."""
    try:
        endpoint = urlsplit(result["endpoint"])
        if (endpoint.scheme != "https" or endpoint.username or endpoint.password
                or endpoint.port not in (None, 443) or endpoint.path not in ("", "/")
                or endpoint.query or endpoint.fragment
                or not any((endpoint.hostname or "").endswith("." + domain)
                           for domain in ("iotbing.com", "tuyaeu.com", "tuyaus.com", "tuyacn.com", "tuyain.com"))):
            raise ValueError()
        for key in ("uid", "access_token", "refresh_token", "terminal_id"):
            if not isinstance(result[key], str) or not 1 <= len(result[key]) <= 1024:
                raise ValueError()
        if (type(result["t"]) is not int or result["t"] <= 0
                or type(result["expire_time"]) is not int or result["expire_time"] <= 0):
            raise ValueError()
        return {"endpoint": f"https://{endpoint.netloc}", "terminal_id": result["terminal_id"],
                "token_info": {key: result[key] for key in ("uid", "access_token", "refresh_token", "t", "expire_time")}}
    except (KeyError, TypeError, ValueError):
        raise ServiceError(502, "tuya_invalid_login", "Tuya returned invalid account authorization") from None


class TuyaAccount:
    def __init__(self, client):
        self.client = client
        self.specifications = {}
        self.locks = {}
        self.refreshed_credentials = {}

    async def login_request(self, method, user_code, token=None):
        try:
            response = await self.client.request(method, LOGIN_URL + ("/" + quote(token, safe="") if token else ""),
                params={"clientid": CLIENT_ID, "usercode": user_code, **({"schema": "haauthorize"} if token is None else {})})
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (httpx.HTTPError, ValueError):
            raise ServiceError(502, "tuya_login_unavailable", "Unable to reach Tuya account authorization. Try again.") from None

    async def start(self, user_code):
        payload = await self.login_request("POST", user_code)
        token = payload.get("result", {}).get("qrcode") if isinstance(payload.get("result"), dict) else None
        if payload.get("success") is not True or not isinstance(token, str) or not 1 <= len(token) <= 1024:
            raise ServiceError(502, "tuya_login_rejected", "Unable to start Tuya login. Check the User Code in Tuya Smart or Smart Life.")
        buffer = io.BytesIO()
        qrcode.make("tuyaSmart--qrLogin?token=" + token, image_factory=SvgPathImage,
                    error_correction=qrcode.constants.ERROR_CORRECT_Q, border=4).save(buffer)
        return token, "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    async def check(self, user_code, token):
        payload = await self.login_request("GET", user_code, token)
        if payload.get("success") is not True:
            return None
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ServiceError(502, "tuya_invalid_login", "Tuya returned invalid account authorization")
        return account_credentials({**result, "t": payload.get("t")})

    async def execute(self, entry, persist, operation):
        async with self.locks.setdefault(entry['id'], asyncio.Lock()):
            previous = self.refreshed_credentials.get(entry['id'])
            if previous and entry['secret'] == previous[0]:
                entry['secret'] = previous[1]
            old_secret = entry['secret']
            try:
                return await self.execute_locked(entry, persist, operation)
            finally:
                if old_secret != entry['secret']:
                    self.refreshed_credentials[entry['id']] = (old_secret, entry['secret'])

    async def execute_locked(self, entry, persist, operation):
        credentials = json.loads(entry["secret"])
        api = CustomerApi(CustomerTokenInfo(credentials["token_info"]), CLIENT_ID,
                          credentials["user_code"], credentials["endpoint"], None)
        # Only explicit Tuya HTTPS endpoints are permitted; don't follow redirects.
        original_request = api.session.request
        def bounded_request(*args, **kwargs):
            kwargs.update(timeout=10, allow_redirects=False)
            return original_request(*args, **kwargs)
        api.session.request = bounded_request
        api.session.trust_env = False
        def authorized_operation():
            api.refresh_access_token_if_need()
            if api.token_info.expire_time <= int(time.time() * 1000):
                raise ValueError("authorization expired")
            return operation(api)
        worker = asyncio.create_task(asyncio.to_thread(authorized_operation))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            # Finish refresh and persist its token before SQLite/session shutdown.
            await asyncio.gather(worker, return_exceptions=True)
            raise
        except Exception:
            # Never expose vendor exception text (tokens/account identifiers).
            raise ServiceError(502, "tuya_account_unavailable", "Unable to access the Tuya account. Try again or sign in again.") from None
        finally:
            token = api.token_info
            credentials["token_info"] = {"uid": token.uid, "access_token": token.access_token,
                "refresh_token": token.refresh_token, "t": token.expire_time, "expire_time": 0}
            # SDK stores an absolute expiry. t + expire_time*1000 reconstructs it.
            entry["secret"] = json.dumps(credentials)
            persist(entry)
            api.session.close()

    async def devices(self, entry, persist):
        def inventory(api):
            homes = api.get("/v1.0/m/life/users/homes")
            if not isinstance(homes, dict) or homes.get("success") is not True or not isinstance(homes.get("result"), list):
                raise ValueError()
            devices = {}
            for home in homes["result"]:
                response = api.get("/v1.0/m/life/ha/home/devices", {"homeId": str(home["ownerId"])})
                if not isinstance(response, dict) or response.get("success") is not True or not isinstance(response.get("result"), list):
                    raise ValueError()
                for item in response["result"]:
                    key = (entry['id'], entry['uid'], item['id'])
                    specification, expires = self.specifications.get(key, (None, 0))
                    if specification is None or time.monotonic() >= expires:
                        response = api.get("/v1.1/m/life/" + quote(item["id"], safe="") + "/specifications")
                        if not isinstance(response, dict) or response.get("success") is not True or not isinstance(response.get("result"), dict):
                            raise ValueError()
                        specification = response['result']
                        self.specifications[key] = (specification, time.monotonic() + 600)
                    devices[item["id"]] = device_snapshot(item, specification)
            return list(devices.values())
        return await self.execute(entry, persist, inventory)

    async def command(self, entry, persist, external_id, code, value, preceding=None):
        def send(api):
            result = api.post("/v1.1/m/thing/" + quote(external_id, safe="") + "/commands", None,
                              {"commands": [*(preceding or []), {"code": code, "value": value}]})
            if not isinstance(result, dict) or result.get("success") is not True or result.get("result") is not True:
                raise ValueError()
        await self.execute(entry, persist, send)
