import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/builtins/device-model.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext },
}).outputText;
const { needsDeviceFallback, powerState, colorValue, quantize, rgbHue, deviceMetric, primaryMetric, mergeDeviceSnapshots, brightnessFraction, whiteValue, summaryMetrics } =
  await import(
    `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
  );

test('external snapshots update all cards without overwriting an active command or newer state', () => {
  const first = { id: 'one', state: { switch: true }, available: true, state_revision: 4 };
  const second = { id: 'two', state: { switch: false }, available: true, state_revision: 1 };
  const incoming = [{ ...first, state: { switch: false }, state_revision: 3 },
    { ...second, state: { switch: true }, available: false, state_revision: 2 }];
  let merged = mergeDeviceSnapshots([first, second], incoming, new Set());
  assert.equal(merged[0].state.switch, true);
  assert.equal(merged[0].state_revision, 4);
  assert.equal(merged[1].state.switch, true);
  assert.equal(merged[1].available, false);
  merged = mergeDeviceSnapshots([first, second], incoming, new Set(['two']));
  assert.deepEqual(merged[1], second);
  assert.deepEqual(mergeDeviceSnapshots([first, second], [], new Set()), []);
});

test("preset colors convert to Tuya hue and saturation, including white", () => {
  assert.deepEqual(rgbHue("#ff0000"), { h: 0, s: 1 });
  assert.deepEqual(rgbHue("#00ff00"), { h: 120, s: 1 });
  assert.deepEqual(rgbHue("#0000ff"), { h: 240, s: 1 });
  assert.deepEqual(rgbHue("#ffffff"), { h: 0, s: 0 });
});

test("temperature uses advertised scale and unit without becoming writable", () => {
  const device = {
    kind: "wsdcg",
    controls: [],
    state: { temp_current: 235, humidity_value: 480, battery_percentage: 92 },
    status_specs: {
      temp_current: { min: -100, max: 600, scale: 1, unit: "°C" },
      humidity_value: { scale: 1, unit: "%" },
    },
  };
  const metric = primaryMetric(device);
  assert.equal(metric.code, "temp_current");
  assert.equal(metric.number, 23.5);
  assert.equal(metric.unit, "°C");
  assert.equal(metric.min, -10);
  assert.equal(metric.max, 60);
  assert.equal(deviceMetric(device, "humidity_value").number, 48);
  assert.equal(deviceMetric(device, "battery_percentage").unit, "%");
});

test("primary information follows the device purpose and handles missing values", () => {
  const device = {
    controls: [],
    state: {
      percent_state: 70,
      battery_percentage: 90,
      fan_speed_percent: 35,
      temp_set: 220,
    },
    kind: "cl",
  };
  assert.equal(primaryMetric(device).code, "percent_state");
  assert.equal(
    primaryMetric({ ...device, kind: "fs" }).code,
    "fan_speed_percent",
  );
  assert.equal(primaryMetric({ kind: "wsdcg", controls: [], state: {} }), null);
  assert.equal(
    primaryMetric({ kind: "cz", controls: [], state: { switch: false } }).text,
    "Off",
  );
  assert.equal(
    deviceMetric(
      { controls: [], state: { doorcontact_state: true } },
      "doorcontact_state",
    ).text,
    "Open",
  );
  assert.equal(
    primaryMetric({
      kind: "ywbj",
      controls: [],
      state: { temp_current: 250, smoke_sensor_state: "alarm" },
    }).code,
    "smoke_sensor_state",
  );
});

test("color commands preserve brightness and respect both Tuya HSV scales", () => {
  for (const max of [255, 1000]) {
    const control = {
      constraints: {
        h: { min: 0, max: 360 },
        s: { min: 0, max },
        v: { min: 0, max },
      },
    };
    assert.deepEqual(colorValue(control, 120, 1, 0.5), {
      h: 120,
      s: max,
      v: Math.round(max / 2),
    });
    assert.deepEqual(colorValue(control, 0, 0, 1), { h: 0, s: 0, v: max });
  }
});

test("slider conversion follows advertised step and limits", () => {
  assert.equal(quantize(54, { min: 10, max: 1000, step: 10 }), 50);
  assert.equal(quantize(-1, { min: 10, max: 1000 }), 10);
  assert.equal(quantize(1001, { min: 10, max: 1000 }), 1000);
  assert.equal(quantize(1008, { min: 10, max: 1008, step: 10 }), 1000);
});

test("card summaries omit controls while retaining measured values and changed positions", () => {
  const controls = [{ code: 'switch' }, { code: 'temp_set' }, { code: 'mode' }];
  const device = { kind: 'wk', controls, state: { switch: true, temp_current: 215, temp_set: 230, mode: 'heat', humidity_value: 460 } };
  const summary = summaryMetrics(device, controls);
  assert.equal(summary.primary.code, 'temp_current');
  assert.deepEqual(summary.secondary.map(metric => metric.code), ['humidity_value']);
  const fan = { kind: 'fs', controls: [{ code: 'fan_speed_percent' }], state: { fan_speed_percent: 45 } };
  assert.equal(summaryMetrics(fan, fan.controls).primary, null);
  const curtain = { kind: 'cl', controls: [{ code: 'percent_control' }], state: { percent_state: 65, percent_control: 65 } };
  assert.equal(summaryMetrics(curtain, curtain.controls).primary, null);
  curtain.state.percent_control = 80;
  assert.equal(summaryMetrics(curtain, curtain.controls).primary.number, 65);
});

test("danger and detection states are emphasized without flagging normal power or readings", () => {
  const metric = (code, value) => deviceMetric({ controls: [], state: { [code]: value } }, code);
  for (const code of ['smoke_sensor_state', 'gas_sensor_state']) assert.equal(metric(code, 'alarm').severity, 'danger');
  assert.equal(metric('watersensor_state', true).severity, 'danger');
  assert.equal(metric('pir', 'pir').severity, 'warning');
  assert.equal(metric('doorcontact_state', true).severity, 'warning');
  for (const [code, value] of [['switch', true], ['smoke_sensor_state', 'normal'], ['pir', 'none'], ['doorcontact_state', false], ['temp_current', 250]]) assert.equal(metric(code, value).severity, null);
});

test('white selects the native temperature and brightness percentages use the actual channel', () => {
  assert.equal(whiteValue({constraints:{min:1000,max:10000,unit:'K'}}), 4500);
  assert.equal(whiteValue({constraints:{min:5000,max:6500,unit:'K'}}), 5000);
  assert.equal(whiteValue({constraints:{min:0,max:1000}}), 500);
  assert.equal(brightnessFraction(39,{min:1,max:100}), .39);
  assert.equal(brightnessFraction(10,{min:10,max:1000}), .01);
  assert.equal(brightnessFraction(100,{min:1,max:100}), 1);
  assert.equal(quantize(100,{min:1,max:100,step:10,step_origin:0}), 100);
  assert.equal(quantize(39,{min:1,max:100,step:10,step_origin:0}), 40);
  assert.equal(quantize(0,{min:1,max:100,step:10,step_origin:0}), 1);
  const control={constraints:{h:{min:0,max:360},s:{min:0,max:1000},v:{min:10,max:1000}}};
  assert.equal(colorValue(control,120,1,.5).v,500);
  assert.equal(colorValue(control,120,1,0).v,10);
});


test('power distinguishes current off, unknown and stale offline state', () => {
  const device = { available: true, controls: [], state: { switch: false } };
  assert.equal(powerState(device, 'switch'), false);
  assert.equal(deviceMetric(device, 'switch').text, 'Off');
  assert.equal(powerState({ ...device, state: {} }, 'switch'), undefined);
  const offline = { ...device, available: false, state: { switch: true } };
  assert.equal(powerState(offline, 'switch'), undefined);
  assert.equal(deviceMetric(offline, 'switch').text, 'Offline');
  assert.equal(deviceMetric(offline, 'switch').severity, null);
});


test('HTTP is only a fallback when device events are absent or stale', () => {
  assert.equal(needsDeviceFallback(0, 1000), true);
  assert.equal(needsDeviceFallback(1000, 46000), false);
  assert.equal(needsDeviceFallback(1000, 46001), true);
  const device = { available: true, state_stale: true, state: { switch: true }, controls: [] };
  assert.equal(powerState(device, 'switch'), undefined);
  assert.equal(deviceMetric(device, 'switch').text, 'State unknown');
});
