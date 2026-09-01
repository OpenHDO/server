import type { Icon } from "@phosphor-icons/react/lib";
import type { ComponentType } from "react";

export type PanelModuleContext = {
  navigate: (moduleId: string) => void;
  api: {
    request: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
  };
};

export type PanelModuleProps = {
  context: PanelModuleContext;
};

export type PanelModule = {
  id: string;
  label: string;
  icon: Icon;
  component: ComponentType<PanelModuleProps>;
  order?: number;
};

const modules = new Map<string, PanelModule>();
const listeners = new Set<() => void>();
let snapshot: PanelModule[] = [];

export function registerModule(module: PanelModule) {
  if (!module.id || !module.label || modules.has(module.id)) {
    throw new Error(`Panel module id is invalid or already registered: ${module.id}`);
  }
  modules.set(module.id, module);
  snapshot = [...modules.values()].sort((left, right) => (left.order ?? Number.MAX_SAFE_INTEGER) - (right.order ?? Number.MAX_SAFE_INTEGER));
  listeners.forEach((listener) => listener());
}

export function getPanelModules() {
  return snapshot;
}

export function subscribeToModules(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
