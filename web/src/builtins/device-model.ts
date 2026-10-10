export type StateValue = boolean | number | string | Record<string, number>;
type Range = { min: number; max: number; step?: number; step_origin?: number };
export type Control = {
  code: string;
  name: string;
  type: "Boolean" | "Integer" | "Enum" | "Json";
  constraints: {
    relative?: boolean;
    unbounded?: boolean;
    retrievable?: boolean;
    min?: number;
    max?: number;
    step?: number;
    step_origin?: number;
    scale?: number;
    unit?: string;
    range?: string[];
    h?: Range;
    s?: Range;
    v?: Range;
  };
};
export type Device = {
  id: string;
  integration_id: string;
  external_id: string;
  name: string;
  area: string;
  room_id?: string | null;
  enabled: boolean;
  available: boolean;
  state_stale?: boolean;
  kind: string;
  device_type?: string | null;
  kind_override?: 'cz' | 'dj' | null;
  icon?: 'garland' | null;
  state_revision?: number;
  product_name: string;
  state: Record<string, StateValue>;
  controls: Control[];
  status_specs?: Record<string, Control["constraints"]>;
};

export function mergeDeviceSnapshots(previous: Device[], incoming: Device[], pending: Set<string>) {
  const current = new Map(previous.map(device => [device.id, device]));
  return incoming.map(device => {
    const old = current.get(device.id);
    if (old && pending.has(device.id)) return old;
    if (old && (old.state_revision ?? 0) > (device.state_revision ?? 0))
      return { ...device, state: old.state, available: old.available, state_revision: old.state_revision, state_stale: old.state_stale };
    return device;
  });
}

export const metricLabels: Record<string, string> = {
  property_illumination: "Illumination", property_co2_level: "CO₂", property_pressure: "Pressure",
  property_pm1_density: "PM1", "property_pm2.5_density": "PM2.5", property_pm10_density: "PM10", property_tvoc: "TVOC",
  property_electricity_meter: "Electricity consumption", property_gas_meter: "Gas consumption", property_heat_meter: "Heat consumption",
  property_water_meter: "Water consumption", property_meter: "Meter", property_water_level: "Water level", property_food_level: "Food level",
  property_event_battery_level: "Battery status", property_event_food_level: "Food status", property_event_water_level: "Water status",
  vibration: "Vibration", button: "Button", range_volume: "Volume", range_channel: "Channel",
  temp_current: "Temperature",
  temp_current_f: "Temperature",
  temperature: "Temperature",
  temp_set: "Target",
  temp_set_f: "Target",
  humidity_value: "Humidity",
  humidity: "Humidity",
  battery_percentage: "Battery",
  battery_state: "Battery",
  cur_power: "Power",
  cur_voltage: "Voltage",
  cur_current: "Current",
  fan_speed_percent: "Speed",
  fan_speed: "Speed",
  percent_state: "Open",
  percent_control: "Open",
  doorcontact_state: "Contact",
  pir: "Motion",
  smoke_sensor_state: "Smoke",
  watersensor_state: "Water",
  gas_sensor_state: "Gas",
  status: "Status",
  cleaning_state: "Status",
  mode: "Mode",
};

export function powerState(device: Device, code: string): boolean | undefined {
  const value = device.state[code];
  return device.available && !device.state_stale && typeof value === "boolean" ? value : undefined;
}

export function deviceMetric(device: Device, code: string) {
  const raw = device.state[code];
  if (raw === undefined || typeof raw === "object") return null;
  const spec =
    device.status_specs?.[code] ??
    device.controls.find((c) => c.code === code)?.constraints;
  const scale = 10 ** (spec?.scale ?? 0);
  const number =
    typeof raw === "number" && Number.isFinite(raw) ? raw / scale : null;
  const unit =
    spec?.unit ??
    ([
      "battery_percentage",
      "fan_speed_percent",
      "percent_control",
      "percent_state",
    ].includes(code)
      ? "%"
      : "");
  const states: Record<string, string> = {
    true: "Detected",
    false: "Clear",
    open: "Open",
    close: "Closed",
    closed: "Closed",
    none: "Clear",
    pir: "Detected",
    alarm: "Alert", detected: "Detected", not_detected: "Clear", leak: "Alert", dry: "Clear",
    click: "Pressed", double_click: "Double press", long_press: "Long press", fall: "Fall", tilt: "Tilt",
    vibration: "Vibration", empty: "Empty", low: "Low", normal: "Normal", high: "High",
  };
  const power = [
    "switch",
    "switch_1",
    "switch_led",
    "switch_fan",
    "switch_spray",
  ].includes(code);
  const active = (power ? device.available !== false && raw === true : raw === true) || ["alarm", "alert", "detected", "pir", "open", "opened", "warning", "error", "fault", "leak", "fall", "tilt"].includes(String(raw).toLowerCase());
  const severity = !power && active
    ? ["smoke_sensor_state", "gas_sensor_state", "watersensor_state"].includes(code) || ["alarm", "alert", "error", "fault"].includes(String(raw).toLowerCase()) ? "danger" as const : "warning" as const
    : null;
  return {
    code,
    severity,
    label: power ? "Power" : (metricLabels[code] ?? code.replaceAll("_", " ")),
    number,
    text:
      number === null
        ? power && device.state_stale
          ? "State unknown"
          : power && device.available === false
          ? "Offline"
          : power && typeof raw === "boolean"
          ? raw
            ? "On"
            : "Off"
          : code === "doorcontact_state" && typeof raw === "boolean"
            ? raw
              ? "Open"
              : "Closed"
            : (states[String(raw)] ?? String(raw).replaceAll("_", " "))
        : Number(number.toFixed(2)).toLocaleString(),
    unit,
    min: spec?.min === undefined ? undefined : spec.min / scale,
    max: spec?.max === undefined ? undefined : spec.max / scale,
  };
}

export function summaryMetrics(device: Device, displayedControls: Control[]) {
  const displayed = new Set(displayedControls.map(control => control.code));
  const redundant = (code: string) => displayed.has(code)
    || (code === "percent_state" && displayed.has("percent_control") && device.state.percent_state === device.state.percent_control);
  const primary = primaryMetric(device);
  const secondary = ["temp_set", "temp_set_f", "humidity_value", "humidity", "battery_percentage", "battery_state", "cur_voltage", "cur_current", "mode", "status", ...Object.keys(device.state)]
    .filter((code, index, codes) => codes.indexOf(code) === index && code !== primary?.code && !redundant(code) && (!!metricLabels[code] || code in (device.status_specs ?? {})))
    .map(code => deviceMetric(device, code)).filter(metric => metric !== null).slice(0, 3);
  return { primary: primary && !redundant(primary.code) ? primary : null, secondary };
}

export function primaryMetric(device: Device) {
  const priorities =
    device.kind === "fs"
      ? ["fan_speed_percent", "fan_speed"]
      : ["cl", "clkg"].includes(device.kind)
        ? ["percent_state", "percent_control", "control"]
        : ["cz", "pc"].includes(device.kind)
          ? ["cur_power", "cur_current"]
          : ((
              {
                pir: ["pir"],
                mcs: ["doorcontact_state"],
                ywbj: ["smoke_sensor_state"],
                rqbj: ["gas_sensor_state"],
                sj: ["watersensor_state"],
              } as Record<string, string[]>
            )[device.kind] ?? []);
  return (
    [
      ...priorities,
      ...(device.device_type?.startsWith("smart_meter") ? Object.keys(device.status_specs ?? {}) : []),
      "temp_current",
      "temp_current_f",
      "temperature",
      "temp_set",
      "temp_set_f",
      "humidity_value",
      "humidity",
      "doorcontact_state",
      "pir",
      "smoke_sensor_state",
      "watersensor_state",
      "cleaning_state",
      "status",
      "battery_percentage",
      "switch",
      "switch_1",
      "switch_fan",
      "switch_spray",
      ...Object.keys(device.status_specs ?? {}),
    ]
      .map((code) => deviceMetric(device, code))
      .find(Boolean) ?? null
  );
}
export function quantize(value: number, range: Range) {
  const step = range.step || 1;
  if (range.step_origin !== undefined) {
    const snapped = range.step_origin + Math.round((value - range.step_origin) / step) * step;
    return Math.max(range.min, Math.min(range.max, snapped));
  }
  const maximum = range.min + Math.floor((range.max - range.min) / step) * step;
  return Math.max(
    range.min,
    Math.min(
      maximum,
      range.min +
        Math.round((value - range.min) / (range.step || 1)) * (range.step || 1),
    ),
  );
}
export function brightnessFraction(value: StateValue | undefined, range: { min?: number; max?: number }) {
  return typeof value === 'number' ? Math.max(0, Math.min(1, value / (range.max || 100))) : 1;
}

export function whiteValue(control: Control) {
  const range = { min: control.constraints.min ?? 0, max: control.constraints.max ?? 1000, step: control.constraints.step };
  // Native kelvin capabilities and Tuya's normalized white-temperature DP use different scales.
  return quantize(control.constraints.unit === 'K' ? 4500 : (range.min + range.max) / 2, range);
}
export function rgbHue(hex: string) {
  const [r, g, b] = [1, 3, 5].map(
    (i) => parseInt(hex.slice(i, i + 2), 16) / 255,
  );
  const max = Math.max(r, g, b),
    min = Math.min(r, g, b),
    d = max - min;
  return {
    h: d
      ? ((max === r
          ? (g - b) / d
          : max === g
            ? (b - r) / d + 2
            : (r - g) / d + 4) *
          60 +
          360) %
        360
      : 0,
    s: max ? d / max : 0,
  };
}
export function colorValue(
  control: Control,
  h: number,
  s: number,
  brightness: number,
) {
  return Object.fromEntries(
    [
      ["h", h / 360],
      ["s", s],
      ["v", brightness],
    ].map(([key, fraction]) => {
      const range = control.constraints[key as "h" | "s" | "v"]!;
      return [
        key,
        quantize(key === 'v' ? Number(fraction) * range.max : range.min + Number(fraction) * (range.max - range.min), range),
      ];
    }),
  );
}
export function controlLabel(control: Control) {
  const labels: Record<string, string> = {
    range_volume: "Volume", range_channel: "Channel", humidity_set: "Target humidity",
    video_stream: "View camera", toggle_backlight: "Backlight", toggle_controls_locked: "Child lock", toggle_ionization: "Ionization",
    toggle_keep_warm: "Keep warm", toggle_mute: "Mute", toggle_oscillation: "Oscillation", toggle_pause: "Pause",
    mode_cleanup_mode: "Cleaning mode", mode_coffee_mode: "Coffee", mode_dishwashing: "Dishwashing",
    mode_fan_speed: "Fan speed", mode_heat: "Heating mode", mode_input_source: "Input source", mode_program: "Program",
    mode_swing: "Air direction", mode_tea_mode: "Tea", mode_thermostat: "Mode", mode_ventilation_mode: "Ventilation mode", mode_work_speed: "Work speed",
    switch_led: "Power",
    switch: "Power",
    bright_value: "Brightness",
    bright_value_v2: "Brightness",
    work_mode: "Mode",
    colour_data: "Color",
    colour_data_v2: "Color",
    temp_value: "Color temperature",
    temp_value_v2: "Color temperature",
    color_scene: "Lighting scene",
    temp_set: "Target temperature",
    temp_set_f: "Target temperature",
    fan_speed: "Fan speed",
    fan_speed_percent: "Fan speed",
    percent_control: "Position",
    control: "Position",
    countdown: "Timer",
    countdown_1: "Timer",
  };
  return labels[control.code] ?? control.name.replaceAll("_", " ");
}

export function needsDeviceFallback(lastEventAt: number, now: number) {
  return lastEventAt === 0 || now - lastEventAt > 45000;
}
