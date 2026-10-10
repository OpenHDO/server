import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { PuzzlePiece } from "@phosphor-icons/react/PuzzlePiece";
import { GearSix } from "@phosphor-icons/react/GearSix";
import { X } from "@phosphor-icons/react/X";
import { extensionList, subscribeExtensions, getExtensionRevision } from "../plugins/registry";
import { Plus } from "@phosphor-icons/react/Plus";
import { Trash } from "@phosphor-icons/react/Trash";
import { useNotifications } from "../notifications";
import { responseError } from "../i18n";
import { syncPlugins } from "../plugins/runtime";
import type { PluginRecord } from "../plugins/sdk";
import type { PanelModuleProps } from "../modules/registry";

const button = "rounded-md border border-neutral-700 px-3 py-2 text-sm hover:border-neutral-500 disabled:opacity-40";
export default function PluginsView({ context }: PanelModuleProps) {
  const { t } = useTranslation();
  const notify = useNotifications();
  useSyncExternalStore(subscribeExtensions, getExtensionRevision);
  const [settings, setSettings] = useState<PluginRecord | null>(null);
  const Settings = settings ? extensionList("settings").find(item => item.id.startsWith(settings.manifest.id + ":"))?.component : undefined;
  const settingsDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (settings) settingsDialog.current?.showModal(); }, [settings]);
  const [plugins, setPlugins] = useState<PluginRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [candidate, setCandidate] = useState<PluginRecord | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const request = context.api.request;
  const refresh = async () => {
    const response = await request("/api/v1/plugins");
    if (!response.ok) throw new Error(await responseError(response));
    setPlugins((await response.json()).plugins);
    await syncPlugins(context, notify);
  };
  useEffect(() => { void refresh().catch((error: Error) => notify("error", error.message)); }, []);
  useEffect(() => { if (candidate) dialog.current?.showModal(); }, [candidate]);
  const action = async (path: string, init: RequestInit, message: string) => {
    if (busy) return;
    setBusy(true);
    try {
      const response = await request(`/api/v1/plugins${path}`, init);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? t("Unable to update plugin"));
      }
      await refresh(); notify("success", t(message));
    } catch (error) { notify("error", error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  };
  return <section className="w-full max-w-4xl space-y-3">
    <div className="flex items-center justify-between gap-3">
      <h1 className="min-w-0 flex-1 font-brand text-xl font-bold sm:text-2xl">{t("Plugins")}</h1>
      <button disabled={busy} className={button} onClick={() => void action("/reload", {method:"POST"}, "Plugins refreshed")}>{t("Refresh")}</button>
      <button disabled={busy} className={`${button} flex items-center gap-2`} onClick={() => file.current?.click()}><Plus size={18}/>{t("Install .hdop")}</button>
      <input ref={file} type="file" accept=".hdop" className="hidden" onChange={(event) => {
        const upload = event.target.files?.[0]; event.target.value = "";
        if (upload && upload.size <= 64 * 1024 * 1024) void action("/install", { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: upload }, "Plugin installed");
        else if (upload) notify("error", t("Plugin exceeds 64 MiB"));
      }}/>
    </div>
    <div className="divide-y divide-neutral-800 rounded-lg bg-neutral-900/50">
      {plugins.map((plugin) => <div key={plugin.manifest.id} className="flex flex-wrap items-center gap-3 px-3 py-3">
        <PuzzlePiece size={24} className="text-neutral-500"/>
        <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{plugin.manifest.name}</div><div className="text-xs text-neutral-500">{plugin.manifest.version} · {t(plugin.status)}</div></div>
        {plugin.status === "enabled" && extensionList("settings").some(item => item.id.startsWith(plugin.manifest.id + ":")) && <button className={button} disabled={busy} aria-label={t("Plugin settings")} onClick={() => setSettings(plugin)}><GearSix size={18}/></button>}
        <button disabled={busy || plugin.status === "invalid"} className={button} onClick={() => plugin.status === "enabled" ? void action(`/${plugin.manifest.id}/disable`, {method:"POST"}, "Plugin disabled") : setCandidate(plugin)}>{t(plugin.status === "enabled" ? "Disable" : "Enable")}</button>
        <button disabled={busy} className={`${button} px-2`} aria-label={t("Remove plugin")} onClick={() => setCandidate({ ...plugin, status: "invalid" })}><Trash size={18}/></button>
        {plugin.error && <button className="text-xs text-red-400" onClick={() => notify("error", plugin.error!)}>{t("Details")}</button>}
      </div>)}
      {!plugins.length && <div className="px-3 py-6 text-sm text-neutral-500">{t("No plugins installed")}</div>}
    </div>
    {settings && <dialog ref={settingsDialog} onCancel={() => setSettings(null)} className="m-auto w-[min(92vw,28rem)] space-y-4 rounded-lg border border-neutral-800 bg-neutral-950 p-4 text-neutral-100 backdrop:bg-black/60">
      <div className="flex items-center justify-between"><h2 className="font-brand text-xl font-semibold">{settings.manifest.name}</h2><button className={button} aria-label={t("Close dialog")} onClick={() => setSettings(null)}><X size={18}/></button></div>
      {Settings && <Settings context={context}/>} 
    </dialog>}
    {candidate && <dialog ref={dialog} onCancel={() => setCandidate(null)} className="m-auto w-[min(92vw,28rem)] rounded-lg border border-neutral-700 bg-neutral-950 p-4 text-neutral-100 backdrop:bg-black/60">
      <h2 className="font-semibold">{candidate.manifest.name}</h2>
      <p className="my-3 text-sm text-neutral-400">{t(candidate.status === "invalid" ? "Remove plugin? Its data will be kept." : "Plugins run trusted code with server and panel access. Enable only plugins you trust.")}</p>
      {candidate.status !== "invalid" && <p className="mb-4 text-xs text-neutral-500">{(candidate.manifest.permissions ?? []).join(", ")}</p>}
      <div className="flex justify-end gap-2"><button className={button} onClick={() => setCandidate(null)}>{t("Cancel")}</button><button className={button} onClick={() => { void action(`/${candidate.manifest.id}${candidate.status === "invalid" ? "" : "/enable"}`, {method:candidate.status === "invalid" ? "DELETE" : "POST"}, candidate.status === "invalid" ? "Plugin removed" : "Plugin enabled"); setCandidate(null); }}>{t(candidate.status === "invalid" ? "Remove" : "Enable")}</button></div>
    </dialog>}
  </section>;
}
