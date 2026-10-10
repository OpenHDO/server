import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

let source = await readFile(new URL("../src/design-preview/fixtures.ts", import.meta.url), "utf8");
const yandex = JSON.parse(await readFile(new URL("../src/design-preview/yandex-fixtures.json", import.meta.url), "utf8"));
source = source.replace('import yandexFixtures from "./yandex-fixtures.json";', `const yandexFixtures = ${JSON.stringify(yandex)};`);
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { createPreviewFixtures, applyPreviewAction, deviceFixtures, previewStates } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

test("preview covers every fixture and state with independent device data", () => {
  const fixtures = createPreviewFixtures();
  assert.equal(fixtures.length, deviceFixtures.length * previewStates.length);
  assert.equal(new Set(fixtures.map(({ device }) => device.id)).size, fixtures.length);
  for (const state of previewStates) assert.equal(fixtures.filter((fixture) => fixture.previewState === state).length, deviceFixtures.length);
  assert.ok(fixtures.filter((fixture) => fixture.previewState === "offline").every(({ device }) => !device.available));
  assert.ok(fixtures.filter((fixture) => fixture.previewState === "disabled").every(({ device }) => !device.enabled));
  assert.ok(fixtures.filter((fixture) => fixture.previewState === "empty").every(({ device }) => Object.keys(device.state).length === 0));
  const index = fixtures.findIndex(({device}) => device.external_id === "light-power");
  fixtures[index].device.state.switch_led = false;
  assert.equal(deviceFixtures.find(({device}) => device.external_id === "light-power").device.state.switch_led, true);
  assert.equal(createPreviewFixtures()[index].device.state.switch_led, true);
});

test("demo actions change only the selected state and synchronize visual modes", () => {
  const device = deviceFixtures.find(({ device }) => device.external_id === "light-rgb-white").device;
  const control = device.controls.find((control) => control.type === "Json");
  const changed = applyPreviewAction(device, control, { h: 240, s: 1000, v: 600 });
  assert.equal(changed.state.work_mode, "colour");
  assert.equal(device.state.work_mode, "white");
  assert.deepEqual(changed.state.colour_data_v2, { h: 240, s: 1000, v: 600 });
  const curtain = deviceFixtures.find(({ device }) => device.external_id === "curtain-position").device;
  const moved = applyPreviewAction(curtain, curtain.controls[0], 80);
  assert.equal(moved.state.percent_state, 80);
  assert.equal(curtain.state.percent_state, 65);
});


test('catalog preview includes every documented type and relative/video controls', async () => {
  const catalog = JSON.parse(await readFile(new URL('../../python/openhdo_server/device_types.json', import.meta.url), 'utf8'));
  assert.deepEqual(new Set(yandex.map(({device}) => device.device_type)), new Set(Object.keys(catalog)));
  assert.ok(yandex.some(({device}) => device.controls.some(control => control.constraints.relative)));
  const camera = yandex.find(({device}) => device.device_type === 'camera').device;
  assert.equal(applyPreviewAction(camera, camera.controls.find(control => control.code === 'video_stream'), 'hls').state.video_stream, 'demo:camera');
  assert.ok(createPreviewFixtures().filter(fixture => fixture.previewState === 'stale').every(({device}) => device.state_stale));
});
