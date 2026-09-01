import type { ComponentType } from "react";

export type PanelItemKind = "builtin" | "custom";

export type PanelItem = {
  id: string;
  label: string;
  kind: PanelItemKind;
  component: ComponentType;
};

const EmptyModule = () => null;

export const builtInModules: PanelItem[] = [
  { id: "overview", label: "Overview", kind: "builtin", component: EmptyModule },
  { id: "lights", label: "Lights", kind: "builtin", component: EmptyModule },
  { id: "linkers", label: "Linkers", kind: "builtin", component: EmptyModule },
  { id: "settings", label: "Settings", kind: "builtin", component: EmptyModule },
];

const customModules: PanelItem[] = [];

// ponytail: build-time registry; add runtime discovery only with a real server module manifest.
export function registerCustomModule(module: Omit<PanelItem, "kind">) {
  if (!module.id || !module.label || builtInModules.some((item) => item.id === module.id) || customModules.some((item) => item.id === module.id)) {
    throw new Error(`Panel module id is invalid or already registered: ${module.id}`);
  }
  customModules.push({ ...module, kind: "custom" });
}

export function getPanelModules() {
  return [...builtInModules, ...customModules];
}
