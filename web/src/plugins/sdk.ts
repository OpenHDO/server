import type * as React from "react";
import type { PanelModule, PanelModuleContext } from "../modules/registry";
import type { Extension, ExtensionKind } from "./registry";

export type PluginManifest = {
  schemaVersion: 1; apiVersion: 1; id: string; name: string; version: string;
  permissions?: string[]; dependencies?: Record<string, number>;
  entrypoints?: { python?: string; web?: string };
  contributes?: Record<string, Array<{ id: string; name?: string; file?: string; [key: string]: unknown }>>;
};
export type PluginRecord = { manifest: PluginManifest; status: "enabled" | "disabled" | "error" | "invalid"; error: string | null; revision: string };
export type ThemeDefinition = { id: string; name: string; base: "dark" | "light"; variables: Record<string, string> };
export interface PluginHost {
  apiVersion: 1;
  id: string;
  React: typeof React;
  t: (key: string, values?: Record<string, string | number>) => string;
  ui: { DeviceCard: React.ComponentType<any> };
  context: PanelModuleContext;
  module: (module: Omit<PanelModule, "icon"> & { icon?: PanelModule["icon"]; replaces?: string }) => void;
  extension: (kind: ExtensionKind, value: Extension) => void;
  extensions: (kind: ExtensionKind) => Extension[];
  theme: (theme: ThemeDefinition) => void;
  language: (code: string, name: string, strings: Record<string, string>, replace?: boolean) => void;
  asset: (path: string) => string;
  request: (path: string, init?: RequestInit) => Promise<Response>;
  notify: (tone: "success" | "error", message: string) => void;
  onDispose: (callback: () => void) => void;
}
export type PluginEntry = { activate: (host: PluginHost) => void | (() => void) | Promise<void | (() => void)> };
