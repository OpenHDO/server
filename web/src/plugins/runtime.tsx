import * as React from "react";
import { PuzzlePiece } from "@phosphor-icons/react/PuzzlePiece";
import { registerModule } from "../modules/registry";
import type { PanelModuleContext } from "../modules/registry";
import { registerExtension, extensionList } from "./registry";
import { registerLanguage, registerTheme, t } from "../i18n";
import type { PluginEntry, PluginHost, PluginRecord, ThemeDefinition } from "./sdk";
import { DeviceCard } from "../builtins/device-card";

const active = new Map<string, { revision: string; dispose: () => void }>();
const reserved = new Set(["users", "settings", "plugins"]);
let loading = Promise.resolve();
let generation = 0;
class PluginBoundary extends React.Component<{ children: React.ReactNode; notify: PluginHost["notify"] }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { this.props.notify("error", error.message); }
  render() { return this.state.failed ? null : this.props.children; }
}

export function syncPlugins(context: PanelModuleContext, notify: PluginHost["notify"]) {
  const requestedGeneration = generation;
  const run = async () => {
    if (requestedGeneration !== generation) return;
    const response = await context.api.request("/api/v1/plugins");
    if (!response.ok) throw new Error("Unable to load plugins");
    const { plugins } = await response.json() as { plugins: PluginRecord[] };
    if (requestedGeneration !== generation) return;
    const enabled = plugins.filter((p) => p.status === "enabled");
    for (const [id, plugin] of active) {
      if (!enabled.some((p) => p.manifest.id === id && p.revision === plugin.revision)) { plugin.dispose(); active.delete(id); }
    }
    const pending = enabled.filter((p) => !active.has(p.manifest.id));
    // Dependencies activate before dependents regardless of inventory order.
    while (pending.length) {
      const index = pending.findIndex((p) => Object.keys(p.manifest.dependencies ?? {}).every((id) => active.has(id)));
      if (index < 0) { notify("error", "Plugin dependency could not be loaded"); break; }
      const record = pending.splice(index, 1)[0];
      const id = record.manifest.id;
      const cleanup: Array<() => void> = [];
      const dispose = () => { for (const callback of cleanup.reverse()) { try { callback(); } catch (error) { console.error(error); } } };
      const asset = (path: string) => `/api/v1/plugins/${encodeURIComponent(id)}/assets/${path.split("/").map(encodeURIComponent).join("/")}?v=${record.revision}`;
      const host: PluginHost = {
        apiVersion: 1, id, React, t, ui: {DeviceCard}, context, asset, notify,
        onDispose: (callback) => { cleanup.push(callback); },
        request: (path, init) => context.api.request(`/api/v1/plugins/${encodeURIComponent(id)}/api/${path}`, init),
        module: (module) => {
          if (module.replaces && reserved.has(module.replaces)) throw new Error("Core administration modules cannot be replaced");
          const Component = module.component;
          cleanup.push(registerModule({ ...module, id: module.replaces ?? `${id}:${module.id}`, icon: module.icon ?? PuzzlePiece,
            component: (props) => <PluginBoundary notify={notify}><Component {...props} /></PluginBoundary> }));
        },
        extensions: extensionList,
        extension: (kind, value) => {
          const key = `${id}:${value.id}`;
          const existing = extensionList(kind).find((item) => item.id === key);
          cleanup.push(registerExtension(kind, { ...existing, ...value, id: key }, kind === "providers"));
        },
        theme: (theme) => { cleanup.push(registerTheme({ ...theme, id: `${id}:${theme.id}` })); },
        language: (code, name, strings, replace) => { cleanup.push(registerLanguage(code, name, strings, replace)); },
      };
      try {
        for (const theme of record.manifest.contributes?.themes ?? []) {
          const result = await context.api.request(asset(theme.file as string));
          if (!result.ok) throw new Error("Theme asset unavailable");
          host.theme(await result.json() as ThemeDefinition);
        }
        for (const language of record.manifest.contributes?.languages ?? []) {
          const result = await context.api.request(asset(language.file as string));
          if (!result.ok) throw new Error("Language asset unavailable");
          host.language(language.id, language.name ?? language.id, await result.json() as Record<string, string>, language.replace === true);
        }
        for (const provider of record.manifest.contributes?.providers ?? []) host.extension("providers", { ...provider, id: provider.id });
        const entry = record.manifest.entrypoints?.web;
        if (requestedGeneration !== generation) { dispose(); return; }
        if (entry) {
          const module = await import(/* @vite-ignore */ asset(entry)) as PluginEntry;
          if (requestedGeneration !== generation) { dispose(); return; }
          const result = await module.activate(host);
          if (result) cleanup.push(result);
        }
        if (requestedGeneration !== generation) { dispose(); return; }
        active.set(id, { revision: record.revision, dispose });
      } catch (error) {
        dispose(); notify("error", `${record.manifest.name}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  };
  loading = loading.catch(() => {}).then(run);
  return loading;
}
export function unloadPlugins() { generation++; for (const item of active.values()) item.dispose(); active.clear(); }
