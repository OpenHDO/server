import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowCounterClockwise } from "@phosphor-icons/react/ArrowCounterClockwise";
import { X } from "@phosphor-icons/react/X";
import { DeviceCard, CompactControl } from "../builtins/device-card";
import type { Control, Device, StateValue } from "../builtins/device-model";
import { applyPreviewAction, createPreviewFixtures, deviceFixtures, previewStates, type PreviewState } from "./fixtures";

const input = "min-w-0 rounded-md border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 focus:outline-none focus:ring-2 focus:ring-accent";
const button = "inline-flex items-center justify-center gap-2 rounded-md border border-neutral-700 px-3 py-2 text-sm hover:border-neutral-500 focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40";
const groups = [...new Set(deviceFixtures.map((fixture) => fixture.group))];

export default function DevicesPreview() {
  const { t } = useTranslation();
  const [fixtures, setFixtures] = useState(createPreviewFixtures);
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState("");
  const [state, setState] = useState<PreviewState | "">("on");
  const [delay, setDelay] = useState(800);
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const busyRef = useRef(new Set<string>());
  const timers = useRef(new Map<string, { timer: number; resolve: (success: boolean) => void }>());
  const [editingId, setEditingId] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const editing = fixtures.find((fixture) => fixture.device.id === editingId)?.device;

  function cancelActions() {
    for (const task of timers.current.values()) {
      window.clearTimeout(task.timer);
      task.resolve(false);
    }
    timers.current.clear();
    busyRef.current.clear();
  }
  useEffect(() => () => cancelActions(), []);
  useEffect(() => {
    if (!editingId) return;
    const origin = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => { dialog.current?.close(); origin?.focus(); };
  }, [editingId]);

  function updateDevice(id: string, update: (device: Device) => Device) {
    setFixtures((current) => current.map((fixture) => fixture.device.id === id ? { ...fixture, device: update(fixture.device) } : fixture));
  }
  function send(id: string, control: Control, value: StateValue): Promise<boolean> {
    if (busyRef.current.has(id)) return Promise.resolve(false);
    busyRef.current.add(id);
    setBusy(new Set(busyRef.current));
    return new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        updateDevice(id, (device) => applyPreviewAction(device, control, value));
        busyRef.current.delete(id);
        timers.current.delete(id);
        setBusy(new Set(busyRef.current));
        resolve(true);
      }, delay);
      timers.current.set(id, { timer, resolve });
    });
  }
  const visible = fixtures.filter((fixture) => (!group || fixture.group === group)
    && (!state || fixture.previewState === state)
    && `${fixture.device.name} ${fixture.device.kind}`.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="w-full max-w-6xl space-y-3">
      <header className="flex items-center justify-between gap-3">
        <h1 className="font-brand text-xl font-bold tracking-tight sm:text-2xl">{t("Devices")}</h1>
        <button className={button} onClick={() => { cancelActions(); setBusy(new Set()); setEditingId(null); setFixtures(createPreviewFixtures()); }}>
          <ArrowCounterClockwise size={16} aria-hidden="true" />{t("Reset")}
        </button>
      </header>
      <div className="flex flex-wrap gap-2">
        <input type="search" className={`${input} w-full sm:w-auto sm:flex-1`} placeholder={t("Search devices…")} aria-label={t("Search devices")} value={search} onChange={(event) => setSearch(event.target.value)} />
        <select className={`${input} flex-1 sm:flex-none`} aria-label="Device type" value={group} onChange={(event) => setGroup(event.target.value)}>
          <option value="">All types</option>
          {groups.map((value) => <option key={value}>{value}</option>)}
        </select>
        <select className={`${input} flex-1 sm:flex-none`} aria-label="Preview state" value={state} onChange={(event) => setState(event.target.value as PreviewState | "")}>
          <option value="">All states</option>
          {previewStates.map((value) => <option key={value} value={value}>{value === "on" ? t("On") : value === "off" ? t("Off") : value === "offline" ? t("Offline") : value === "disabled" ? t("Disabled") : value === "updating" ? "Updating" : value === "stale" ? t("State unknown") : "No data"}</option>)}
        </select>
        <select className={input} aria-label="Action delay" value={delay} onChange={(event) => setDelay(Number(event.target.value))}>
          <option value={0}>0 ms</option><option value={800}>800 ms</option><option value={3000}>3 s</option>
        </select>
      </div>
      {groups.filter((value) => !group || group === value).map((value) => {
        const members = visible.filter((fixture) => fixture.group === value);
        return !members.length ? null : (
          <section key={value} className="space-y-2" aria-label={value}>
            <h2 className="pt-2 text-sm font-medium text-neutral-500">{value}</h2>
            <div className="device-card-list">
              {members.map((fixture) => <DeviceCard key={fixture.device.id} device={fixture.device}
                pending={busy.has(fixture.device.id) || fixture.previewState === "updating"}
                edit={() => setEditingId(fixture.device.id)} send={(control, value) => send(fixture.device.id, control, value)} />)}
            </div>
          </section>
        );
      })}
      {!visible.length && <p className="py-6 text-center text-sm text-neutral-500">{t("No matching devices")}</p>}
      {editing && <dialog ref={dialog} aria-labelledby="preview-settings-title"
        className="fixed inset-0 m-auto max-h-[85dvh] w-[min(32rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-neutral-800 bg-neutral-950 p-4 text-neutral-100 shadow-2xl backdrop:bg-black/65"
        onCancel={() => setEditingId(null)} onClick={(event) => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) setEditingId(null); } }}>
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-2">
            <h2 id="preview-settings-title" className="font-brand text-xl font-semibold">{t("Device settings")}</h2>
            <button className={button} aria-label={t("Close dialog")} onClick={() => setEditingId(null)}><X size={18} /></button>
          </div>
          <label className="block space-y-1 text-sm"><span>{t("Name")}</span><input className={`${input} w-full`} value={editing.name} maxLength={128} onChange={(event) => updateDevice(editing.id, (device) => ({ ...device, name: event.target.value }))} /></label>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" checked={editing.available} onChange={(event) => updateDevice(editing.id, (device) => ({ ...device, available: event.target.checked }))} />Online</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={editing.enabled} onChange={(event) => updateDevice(editing.id, (device) => ({ ...device, enabled: event.target.checked }))} />{t("Enabled")}</label>
          </div>
          {editing.controls.map((control) => <CompactControl key={control.code} control={control} value={editing.state[control.code]}
            disabled={busy.has(editing.id) || !editing.available || !editing.enabled || fixtures.find((fixture) => fixture.device.id === editing.id)?.previewState === "updating"}
            send={(value) => send(editing.id, control, value)} />)}
        </div>
      </dialog>}
    </div>
  );
}
