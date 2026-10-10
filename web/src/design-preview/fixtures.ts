import yandexFixtures from "./yandex-fixtures.json";
import type { Control, Device, StateValue } from "../builtins/device-model";

export type PreviewState = "on" | "off" | "offline" | "disabled" | "updating" | "empty" | "stale";
export type PreviewFixture = { group: string; device: Device; previewState: PreviewState };
export const previewStates: PreviewState[] = ["on", "off", "offline", "disabled", "updating", "empty", "stale"];

const boolean = (code = "switch", name = "Power"): Control => ({ code, name, type: "Boolean", constraints: {} });
const range = (code: string, name: string, min = 0, max = 100, unit = "%", scale = 0): Control => ({
  code, name, type: "Integer", constraints: { min, max, step: 1, scale, unit },
});
const mode = (code: string, values: string[], name = "Mode"): Control => ({ code, name, type: "Enum", constraints: { range: values } });
const color = (code = "colour_data_v2", max = 1000): Control => ({
  code, name: "Color", type: "Json", constraints: { h: { min: 0, max: 360 }, s: { min: 0, max }, v: { min: 0, max } },
});
const power = boolean(), lightPower = boolean("switch_led");
const brightness = range("bright_value_v2", "Brightness", 10, 1000, "");
const white = range("temp_value", "Color temperature", 2700, 6500, "K");
const temperature = range("temp_set", "Target temperature", 160, 300, "°C", 1);
const statusSpecs = {
  temp_current: { min: -100, max: 500, unit: "°C", scale: 1 },
  humidity_value: { min: 0, max: 1000, unit: "%", scale: 1 },
  cur_power: { unit: "W", scale: 1 }, cur_voltage: { unit: "V", scale: 1 }, cur_current: { unit: "A", scale: 3 },
};

function fixture(id: string, group: string, name: string, kind: string, controls: Control[] = [], state: Record<string, StateValue> = {}, icon?: "garland"): PreviewFixture {
  return { group, previewState: "on", device: {
    id: `preview-${id}`, external_id: id, integration_id: "design-preview", name, kind,
    area: "", room_id: null, enabled: true, available: true, product_name: id, controls, state,
    status_specs: statusSpecs, ...(icon ? { icon } : {}),
  } };
}

// These fixtures intentionally exercise the same normalized controls as real provider devices.
export const deviceFixtures: PreviewFixture[] = [
  ...(yandexFixtures as unknown as PreviewFixture[]),
  fixture("light-power", "Lighting", "Light · power only", "dj", [lightPower], { switch_led: true }),
  fixture("light-dimmer", "Lighting", "Light · dimmable", "dj", [lightPower, brightness], { switch_led: true, bright_value_v2: 650 }),
  fixture("light-white", "Lighting", "Light · tunable white", "dj", [lightPower, brightness, white], { switch_led: true, bright_value_v2: 650, temp_value: 4000 }),
  fixture("light-rgb", "Lighting", "Light · RGB", "dj", [lightPower, brightness, color()], { switch_led: true, bright_value_v2: 700, colour_data_v2: { h: 280, s: 800, v: 700 }, work_mode: "colour" }),
  fixture("light-rgb-white", "Lighting", "Light · RGB + white", "dj", [lightPower, brightness, color(), white], { switch_led: true, bright_value_v2: 600, colour_data_v2: { h: 120, s: 1000, v: 600 }, temp_value: 3500, work_mode: "white" }),
  fixture("light-hsv100", "Lighting", "Light · HSV 100", "dj", [lightPower, range("bright_value", "Brightness", 1, 100), color("colour_data_v2", 100)], { switch_led: true, bright_value: 39, colour_data_v2: { h: 240, s: 96, v: 39 }, work_mode: "colour" }),
  fixture("light-hsv255", "Lighting", "Light · HSV 255", "dj", [lightPower, brightness, color("colour_data", 255)], { switch_led: true, colour_data: { h: 20, s: 230, v: 160 }, work_mode: "colour", bright_value_v2: 630 }),
  fixture("strip-scenes", "Lighting", "LED strip · scenes", "dd", [lightPower, brightness, color(), white, mode("color_scene", ["party", "reading", "romance", "night"], "Lighting scene")], { switch_led: true, bright_value_v2: 400, colour_data_v2: { h: 180, s: 1000, v: 400 }, temp_value: 3000, color_scene: "party", work_mode: "colour" }),
  ...[["xdd", "Ceiling light"], ["fwd", "Ambient light"], ["dc", "String light"], ["gyd", "Night light"], ["fsd", "Spotlight"]].map(([kind, name]) => fixture(kind, "Lighting", name, kind, [lightPower, brightness], { switch_led: true, bright_value_v2: 550 })),
  fixture("socket-simple", "Switches & sockets", "Socket · power only", "cz", [power], { switch: true }),
  fixture("socket-metered", "Switches & sockets", "Socket · energy monitoring", "cz", [power], { switch: true, cur_power: 1245, cur_voltage: 2304, cur_current: 540 }),
  fixture("garland-socket", "Switches & sockets", "Socket · garland", "cz", [power], { switch: true }, "garland"),
  fixture("power-strip", "Switches & sockets", "Power strip · 4 outlets", "pc", [boolean("switch_1", "Outlet 1"), boolean("switch_2", "Outlet 2"), boolean("switch_3", "Outlet 3"), boolean("switch_4", "Outlet 4")], { switch_1: true, switch_2: false, switch_3: true, switch_4: false, cur_power: 825 }),
  fixture("switch", "Switches & sockets", "Wall switch", "kg", [power], { switch: true }),
  fixture("switch-dual", "Switches & sockets", "Wall switch · 2 channels", "kg", [boolean("switch_1", "Channel 1"), boolean("switch_2", "Channel 2")], { switch_1: true, switch_2: false }),
  fixture("thermostat", "Climate", "Thermostat", "wk", [power, temperature, mode("mode", ["heat", "eco", "auto"])], { switch: true, temp_current: 215, temp_set: 230, humidity_value: 460, mode: "heat" }),
  fixture("air-conditioner", "Climate", "Air conditioner", "wk", [power, temperature, range("fan_speed", "Fan speed", 1, 5, ""), mode("mode", ["cool", "heat", "dry", "auto"])], { switch: true, temp_current: 268, temp_set: 220, fan_speed: 3, mode: "cool" }),
  fixture("fan", "Climate", "Fan · speed & modes", "fs", [boolean("switch_fan"), range("fan_speed_percent", "Fan speed"), mode("mode", ["normal", "sleep", "natural"])], { switch_fan: true, fan_speed_percent: 45, mode: "normal" }),
  fixture("humidifier", "Climate", "Humidifier", "jsq", [boolean("switch_spray"), mode("mode", ["auto", "low", "high"])], { switch_spray: true, humidity_value: 420, temp_current: 224, mode: "auto" }),
  fixture("temperature-sensor", "Sensors", "Temperature + humidity sensor", "wsdcg", [], { temp_current: 235, humidity_value: 480, battery_percentage: 92 }),
  fixture("temperature-cold", "Sensors", "Temperature sensor · below zero", "wsdcg", [], { temp_current: -65, battery_percentage: 15 }),
  fixture("humidity-sensor", "Sensors", "Humidity sensor", "humidity", [], { humidity_value: 625, battery_percentage: 80 }),
  fixture("motion-clear", "Sensors", "Motion sensor · clear", "pir", [], { pir: "none", battery_percentage: 89 }),
  fixture("motion-detected", "Sensors", "Motion sensor · detected", "pir", [], { pir: "pir", battery_percentage: 89 }),
  fixture("contact-closed", "Sensors", "Contact sensor · closed", "mcs", [], { doorcontact_state: false, battery_percentage: 75 }),
  fixture("contact-open", "Sensors", "Contact sensor · open", "mcs", [], { doorcontact_state: true, battery_percentage: 75 }),
  fixture("smoke-normal", "Sensors", "Smoke sensor · normal", "ywbj", [], { smoke_sensor_state: "normal", battery_percentage: 96 }),
  fixture("smoke-alarm", "Sensors", "Smoke sensor · alarm", "ywbj", [], { smoke_sensor_state: "alarm", battery_percentage: 96 }),
  fixture("gas-normal", "Sensors", "Gas sensor · normal", "rqbj", [], { gas_sensor_state: "normal" }),
  fixture("gas-alarm", "Sensors", "Gas sensor · alarm", "rqbj", [], { gas_sensor_state: "alarm" }),
  fixture("leak-clear", "Sensors", "Leak sensor · clear", "sj", [], { watersensor_state: false, battery_percentage: 67 }),
  fixture("leak-detected", "Sensors", "Leak sensor · detected", "sj", [], { watersensor_state: true, battery_percentage: 67 }),
  fixture("curtain-position", "Curtains", "Curtain · position", "cl", [range("percent_control", "Position")], { percent_control: 65, percent_state: 65, battery_percentage: 90 }),
  fixture("curtain-commands", "Curtains", "Curtain · open / stop / close", "clkg", [mode("control", ["open", "stop", "close"], "Position")], { control: "stop", percent_state: 35 }),
  fixture("vacuum", "Other devices", "Robot vacuum · cleaning", "sd", [power, mode("mode", ["auto", "spot", "edge"])], { switch: true, cleaning_state: "cleaning", battery_percentage: 78, mode: "auto" }),
  fixture("vacuum-docked", "Other devices", "Robot vacuum · docked", "sd", [power], { switch: false, cleaning_state: "charging", battery_percentage: 34 }),
  fixture("camera", "Other devices", "Security camera", "sp", [power], { switch: true }),
  fixture("speaker", "Other devices", "Smart speaker · read only", "speaker"),
  fixture("speaker-controlled", "Other devices", "Smart speaker · controls", "speaker", [power, range("range_volume", "Volume"), boolean("toggle_mute", "Mute")], { switch: true, range_volume: 35, toggle_mute: false }),
  fixture("generic", "Other devices", "Unknown device · generic controls", "device", [power, range("range_custom", "Custom range"), mode("mode_custom", ["auto", "manual"], "Custom mode"), boolean("toggle_custom", "Custom switch")], { switch: true, range_custom: 50, mode_custom: "auto", toggle_custom: false }),
  fixture("long-name", "Other devices", "Smart device with a very long public name to check truncation on small screens", "device", [power], { switch: true }),
];

export function createPreviewFixtures(): PreviewFixture[] {
  return deviceFixtures.flatMap((source) => previewStates.map((previewState) => {
    const device = structuredClone(source.device);
    device.id += `-${previewState}`;
    device.name += ` · ${previewState}`;
    device.available = previewState !== "offline" && previewState !== "disabled";
    device.enabled = previewState !== "disabled";
    device.state_stale = previewState === "stale";
    if (previewState === "empty") device.state = {};
    if (previewState === "off") {
      for (const control of device.controls) {
        if (control.type === "Boolean" && control.code.startsWith("switch")) device.state[control.code] = false;
      }
    }
    return { group: source.group, device, previewState };
  }));
}

export function applyPreviewAction(device: Device, control: Control, value: StateValue): Device {
  const state = { ...device.state, [control.code]: value };
  if (control.code === 'video_stream') state.video_stream = 'demo:camera';
  if (control.constraints.relative) {
    if (typeof device.state[control.code] === 'number' && typeof value === 'number') state[control.code] = Number(device.state[control.code]) + value;
    else delete state[control.code];
  }
  if (control.constraints.retrievable === false && control.code !== 'video_stream') delete state[control.code];
  if (control.code.startsWith("colour_data")) state.work_mode = "colour";
  if (["temp_value", "temp_value_v2"].includes(control.code)) state.work_mode = "white";
  if (control.code === "color_scene") state.work_mode = "scene";
  if (control.code === "percent_control") state.percent_state = value;
  return { ...device, state };
}
