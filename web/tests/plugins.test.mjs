import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

async function load(path) {
  const source = await readFile(new URL(path, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
}
const registry = await load("../src/plugins/registry.ts");
const modules = await load("../src/modules/registry.ts");
const preferences = await load("../src/preferences.ts");

test("plugin device renderer priority and disposal restore the previous renderer", () => {
  const base = registry.registerExtension("deviceModels", {id:"base:lamp",kind:"dj",priority:0});
  const override = registry.registerExtension("deviceModels", {id:"custom:lamp",kind:"dj",priority:10});
  assert.equal(registry.extensionList("deviceModels")[0].id, "custom:lamp");
  override(); assert.equal(registry.extensionList("deviceModels")[0].id, "base:lamp");
  base(); assert.equal(registry.extensionList("deviceModels").length, 0);
});
test("disabled modules leave navigation and duplicate registrations fail", () => {
  const dispose = modules.registerModule({id:"test:main",label:"Test",component:()=>null});
  assert.throws(() => modules.registerModule({id:"test:main",label:"Duplicate"}));
  assert.equal(modules.getPanelModules()[0].id, "test:main");
  dispose(); assert.equal(modules.getPanelModules().length, 0);
});
test("a custom provider login augments metadata and restores it on disposal", () => {
  const base = {id:"test:cloud",name:"Cloud"};
  const disposeBase = registry.registerExtension("providers", base);
  const disposeCustom = registry.registerExtension("providers", {...base,component:()=>null}, true);
  assert.equal(typeof registry.extensionList("providers")[0].component, "function");
  disposeCustom(); assert.equal(registry.extensionList("providers")[0], base);
  disposeBase(); assert.equal(registry.extensionList("providers").length, 0);
});
test("plugin preference ids survive a page reload before plugins load", () => {
  assert.deepEqual(preferences.parsePreferences('{"language":"de","theme":"example:violet"}'), {language:"de",theme:"example:violet"});
  assert.deepEqual(preferences.parsePreferences('{"language":"../bad","theme":"<bad>"}'), preferences.defaults);
});

test("signing out prevents a pending inventory response from reactivating plugins", async () => {
  const source = await readFile(new URL('../src/plugins/runtime.tsx', import.meta.url), 'utf8');
  const globals = `const React = {Component: class {}};
    let registrations = 0;
    const registerExtension = () => {registrations++; return () => {};};
    const extensionList = () => [];
    const DeviceCard = () => null;
    const t = key => key;
    export function registrationCount() {return registrations;}
  `;
  const compiled = ts.transpileModule(globals + source.replace(/^import .*;\r?$/gm, ''), {
    compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React}
  }).outputText;
  const runtime = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
  let resolveRequest;
  const inventory = new Promise(resolve => {resolveRequest = resolve;});
  let started;
  const requestStarted = new Promise(resolve => {started = resolve;});
  const pending = runtime.syncPlugins({api:{request: () => {started(); return inventory;}}}, () => {});
  await requestStarted;
  runtime.unloadPlugins();
  resolveRequest({ok: true, json: async () => ({plugins:[{status:'enabled', revision:'1', manifest:{id:'test.cloud', contributes:{providers:[{id:'cloud'}]}}}]})});
  await pending;
  assert.equal(runtime.registrationCount(), 0);
});
