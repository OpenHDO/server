"""Keep the public Light v1 client API backed by built-in Tuya devices."""
import asyncio
import colorsys
import json
from uuid import uuid4

from fastapi import APIRouter, Depends

from .integrations import DeviceAction
from .models import LightPatchRequest, LightCommandEnvelope, utc_now
from .service import ServiceError


def light_view(device):
    controls = {control["code"]: control for control in device["controls"]}
    power = controls.get("switch_led")
    brightness = controls.get("bright_value_v2") or controls.get("bright_value")
    if power is None or brightness is None:
        return None
    rules = brightness["constraints"]
    color = controls.get("colour_data_v2") or controls.get("colour_data")
    color = color if color and color["type"] == "Json" else None
    capability = {"kind": "light", "power": True, "brightness": {"min": 0, "max": 255}}
    rgb = {"r": 0, "g": 0, "b": 0}
    if color:
        capability.update(color_modes=["RGB"], rgb_channel_range={"min": 0, "max": 255})
        hsv = device["state"].get(color["code"])
        if isinstance(hsv, dict) and all(type(hsv.get(key)) in {int, float} for key in ("h", "s", "v")):
            ranges = color["constraints"]
            channels = colorsys.hsv_to_rgb(hsv["h"] / 360, hsv["s"] / max(1, ranges["s"]["max"]), hsv["v"] / max(1, ranges["v"]["max"]))
            rgb = dict(zip(("r", "g", "b"), [max(0, min(255, round(channel * 255))) for channel in channels]))
    state = None
    actual_brightness = device["state"].get(brightness["code"])
    if color and device['state'].get('work_mode') == 'colour' and isinstance(device['state'].get(color['code']), dict):
        actual_brightness = device['state'][color['code']].get('v')
        rules = color['constraints']['v']
    if device["available"] and type(device["state"].get(power["code"])) is bool and type(actual_brightness) is int:
        state = {"light_id": device["id"], "power": device["state"][power["code"]], "brightness": max(0, min(255, round(actual_brightness * 255 / max(1, rules["max"])))), "rgb_color": rgb, "state_revision": device["state_revision"]}
    return {"light_id": device["id"], "name": device["name"], "linker_id": device["integration_id"], "capability": capability, "state": state, "updated_at": device["updated_at"]}


def lights_router(manager, require_authorization, require_user, require_csrf, instance_name):
    router = APIRouter(prefix="/api/v1")
    command_lock = asyncio.Lock()

    def get(light_id):
        view = light_view(manager.device(light_id))
        if view is None:
            raise ServiceError(404, "light_not_found", "Device does not expose the Light v1 capabilities")
        return view

    async def submit(light_id, change, command_id=None, correlation_id=None):
        async with command_lock:
            fingerprint = change.model_dump_json(exclude={"idempotency_key"})
            previous = manager.db.execute("SELECT * FROM light_commands WHERE device_id=? AND key=?", (light_id, change.idempotency_key)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ServiceError(409, "idempotency_conflict", "Key was used for another command")
                return json.loads(previous["result"])
            get(light_id)
            device = manager.device(light_id)
            controls = {control["code"]: control for control in device["controls"]}
            if change.power is not None:
                code, value = "switch_led", change.power
            elif change.brightness is not None:
                code = "bright_value_v2" if "bright_value_v2" in controls else "bright_value"
                ranges = controls[code]["constraints"]
                color_code = next((key for key in ('colour_data_v2','colour_data') if key in controls), None)
                hsv = device['state'].get(color_code) if color_code else None
                colored = device['state'].get('work_mode') == 'colour' and isinstance(hsv, dict)
                if colored:
                    ranges = controls[color_code]['constraints']['v']
                origin = ranges.get('step_origin', ranges['min'])
                step = ranges.get('step', 1)
                maximum = ranges['max'] if 'step_origin' in ranges else origin + (ranges['max'] - origin) // step * step
                value = max(ranges['min'], min(maximum, origin + round((change.brightness * ranges['max'] / 255 - origin) / step) * step))
                if colored:
                    code, value = color_code, {**hsv, 'v': value}
            else:
                code = "colour_data_v2" if "colour_data_v2" in controls else "colour_data"
                if code not in controls or controls[code]["type"] != "Json":
                    raise ServiceError(422, "unsupported_action", "Light does not support RGB")
                hsv = colorsys.rgb_to_hsv(change.rgb_color.r / 255, change.rgb_color.g / 255, change.rgb_color.b / 255)
                value = {}
                for key, fraction in zip(("h", "s", "v"), hsv):
                    ranges = controls[code]["constraints"][key]
                    step = ranges.get("step", 1)
                    value[key] = min(ranges["max"], ranges["min"] + round(fraction * (ranges["max"] - ranges["min"]) / step) * step)
            await manager.action(light_id, DeviceAction(code=code, value=value))
            command_id = command_id or uuid4()
            result = {"v": 1, "id": str(uuid4()), "type": "command.result", "ts": utc_now().isoformat(), "source": instance_name, "correlation_id": str(correlation_id or command_id), "payload": {"status": "accepted", "light_id": light_id, "command_id": str(command_id), "idempotency_key": change.idempotency_key, "state": None, "error": None}}
            with manager.db:
                manager.db.execute("INSERT INTO light_commands VALUES(?,?,?,?)", (light_id, change.idempotency_key, fingerprint, json.dumps(result)))
            return result

    @router.get("/lights", dependencies=[Depends(require_authorization)])
    async def list_lights():
        return {"lights": [view for device in manager.devices() if (view := light_view(device)) is not None]}

    @router.get("/lights/{light_id}", dependencies=[Depends(require_authorization)])
    async def get_light(light_id: str):
        return get(light_id)

    @router.patch("/lights/{light_id}", status_code=202, dependencies=[Depends(require_user), Depends(require_csrf)])
    async def patch_light(light_id: str, change: LightPatchRequest):
        return await submit(light_id, change)

    @router.post("/lights/{light_id}/commands", status_code=202, dependencies=[Depends(require_user), Depends(require_csrf)])
    async def command(light_id: str, command: LightCommandEnvelope):
        if command.payload.light_id != light_id:
            raise ServiceError(409, "light_mismatch", "Path and payload light IDs differ")
        change = LightPatchRequest.model_validate(command.payload.model_dump(exclude={"command_id", "light_id"}))
        return await submit(light_id, change, command.payload.command_id, command.id)

    return router
