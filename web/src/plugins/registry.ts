import type { ComponentType } from "react";

export type ExtensionKind = "widgets" | "deviceModels" | "flowNodes" | "settings" | "providers";
export type Extension = { id: string; name?: string; kind?: string; component?: ComponentType<any>; [key: string]: unknown };
const registries = new Map<ExtensionKind, Map<string, Extension>>();
const listeners = new Set<() => void>();
let revision = 0;
export const getExtensionRevision = () => revision;
export const subscribeExtensions = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export function extensionList(kind: ExtensionKind) { return [...(registries.get(kind)?.values() ?? [])].sort((a, b) => Number(b.priority ?? 0) - Number(a.priority ?? 0)); }
export function registerExtension(kind: ExtensionKind, value: Extension, replace = false) {
  const registry = registries.get(kind) ?? new Map<string, Extension>();
  registries.set(kind, registry);
  const previous = registry.get(value.id);
  if (previous && !replace) throw new Error(`Duplicate extension: ${value.id}`);
  registry.set(value.id, value);
  const emit = () => { revision++; listeners.forEach((listener) => listener()); };
  emit();
  return () => { if (previous) registry.set(value.id, previous); else registry.delete(value.id); emit(); };
}
