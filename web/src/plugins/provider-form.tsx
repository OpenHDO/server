import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Extension } from "./registry";
import type { PanelModuleContext } from "../modules/registry";
import { useNotifications } from "../notifications";

type Field = { key: string; label: string; type?: "text" | "password" | "number" | "checkbox"; required?: boolean };
export default function ProviderForm({ provider, context, integration, connected, back }: { provider: Extension; context: PanelModuleContext; integration?: { id: string; name: string } | null; connected: () => void; back: () => void }) {
  const { t } = useTranslation();
  const notify = useNotifications();
  const [busy, setBusy] = useState(false);
  const CustomLogin = provider.component;
  const fields = (provider.fields ?? []) as Field[];
  const input = "w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm";
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const data = new FormData(event.currentTarget);
    const config = Object.fromEntries(fields.map((field) => [field.key, field.type === "checkbox" ? data.has(field.key) : field.type === "number" ? Number(data.get(field.key)) : data.get(field.key)]));
    setBusy(true);
    try {
      const response = await context.api.request(`/api/v1/plugins/providers/${encodeURIComponent(provider.id)}/connect`, {method:"POST", headers:{"Content-Type":"application/json"},body:JSON.stringify({name:data.get("integration_name"), config, integration_id:integration?.id})});
      if (!response.ok) { const error = await response.json(); throw new Error(error.detail ?? "Unable to connect provider"); }
      notify("success", t("Integration connected")); connected();
    } catch (error) { notify("error", error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  if (CustomLogin) return <CustomLogin provider={provider} context={context} integration={integration} connected={connected} back={back}/>;
  return <form onSubmit={(event) => void submit(event)} className="space-y-3">
    <label className="block space-y-1 text-sm">{t("Name")}<input className={input} name="integration_name" required maxLength={128} defaultValue={integration?.name ?? provider.name ?? provider.id}/></label>
    {fields.map((field) => <label key={field.key} className="block space-y-1 text-sm">{t(field.label)}<input className={input} type={field.type ?? "text"} name={field.key} required={field.required} autoComplete="off"/></label>)}
    <div className="flex justify-between"><button type="button" onClick={back} className={input}>{t("Back")}</button><button disabled={busy} className={input}>{t("Connect")}</button></div>
  </form>;
}
