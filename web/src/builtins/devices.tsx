import { useTranslation } from "react-i18next";
import { t, responseError, metricText, enumLabel } from "../i18n";
import TuyaLogin from "./tuya-login";
import ProviderForm from "../plugins/provider-form";
import { extensionList, subscribeExtensions, getExtensionRevision } from "../plugins/registry";
import { useNotifications } from "../notifications";
import RoomsView, { type Room } from "./rooms";
import { SlidersHorizontal } from "@phosphor-icons/react/SlidersHorizontal";
import { Trash } from "@phosphor-icons/react/Trash";
import { deviceMetric, mergeDeviceSnapshots, needsDeviceFallback } from "./device-model";
import {
  DeviceCard,
  CompactControl,
  type Device,
  type Control,
  type StateValue,
} from "./device-card";
import { Devices } from "@phosphor-icons/react/Devices";
import { PuzzlePiece } from "@phosphor-icons/react/PuzzlePiece";
import { Plus } from "@phosphor-icons/react/Plus";
import { X } from "@phosphor-icons/react/X";
import { useEffect, useRef, useState, type FormEvent, useSyncExternalStore } from "react";
import type { PanelModuleProps } from "../modules/registry";

type Integration = {
  id: string;
  provider: string;
  name: string;
  status: string;
  error: string | null;
  synced_at: string | null;
  device_count: number;
};
const button =
  "inline-flex items-center justify-center gap-2 rounded-md border border-neutral-700 px-3 py-2 text-sm transition hover:border-neutral-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40 disabled:pointer-events-none";
const input =
  "w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 focus:outline-none focus:ring-2 focus:ring-accent";

export default function DevicesView({ context }: PanelModuleProps) {
  const { t } = useTranslation();
  const notify = useNotifications();
  useSyncExternalStore(subscribeExtensions, getExtensionRevision);
  const providerExtensions = extensionList("providers");
  const pendingRef = useRef(false);
  const devicePendingRef = useRef(new Set<string>());
  const deviceEventsRef = useRef(0);
  const lastEventAtRef = useRef(0);
  const [devicePending, setDevicePending] = useState(new Set<string>());
  const dialogRef = useRef<HTMLElement>(null);
  const [providerSelected, setProviderSelected] = useState<string | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [form, setForm] = useState<Integration | "new" | null>(null);
  const [editing, setEditing] = useState<Device | null>(null);
  const [deleting, setDeleting] = useState<Integration | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [tab, setTab] = useState<"devices" | "integrations" | "rooms">(
    "devices",
  );
  const selectedExtension = providerExtensions.find(provider => provider.id === providerSelected);
  const admin = context.auth.user?.role === "admin";
  useEffect(() => {
    if (error) notify("error", error);
  }, [error, notify]);

  async function api(path: string, method = "GET", body?: unknown) {
    const response = await context.api.request(`/api/v1/${path}`, {
      method,
      ...(body === undefined
        ? {}
        : {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }),
    });
    if (!response.ok) {
      throw new Error(await responseError(response));
    }
    return response.status === 204 ? null : response.json();
  }

  async function load() {
    const eventRevision = deviceEventsRef.current;
    const [homes, inventory, roomList] = await Promise.all([
      api("integrations"),
      api("devices"),
      api("rooms"),
    ]);
    if (eventRevision === deviceEventsRef.current) {
      setIntegrations(homes.integrations as Integration[]);
      setDevices(previous => mergeDeviceSnapshots(previous, inventory.devices as Device[], devicePendingRef.current));
      setRooms(roomList.rooms as Room[]);
    }
  }

  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        if (active) {
          await load();
          setError(null);
        }
      } catch (reason) {
        if (active)
          setError(
            reason instanceof Error ? reason.message : t("Unable to load devices"),
          );
      } finally {
        if (active) setLoading(false);
      }
    }
    void refresh();
    const timer = window.setInterval(() => {
      if (needsDeviceFallback(lastEventAtRef.current, Date.now())) void refresh();
    }, 10000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let active = true;
    let socket: WebSocket;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      if (!active) return;
      const url = new URL('/api/v1/events?devices=1', window.location.href);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(url);
      socket.onmessage = event => {
        if (!active) return;
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'devices.heartbeat') lastEventAtRef.current = Date.now();
          if (message.type === 'devices.updated' && Array.isArray(message.payload?.devices)) {
            lastEventAtRef.current = Date.now();
            if (Array.isArray(message.payload.integrations)) setIntegrations(message.payload.integrations as Integration[]);
            if (Array.isArray(message.payload.rooms)) setRooms(message.payload.rooms as Room[]);
            deviceEventsRef.current += 1;
            setDevices(previous => mergeDeviceSnapshots(previous, message.payload.devices as Device[], devicePendingRef.current));
          }
        } catch { /* Periodic HTTP refresh remains available if an event is invalid. */ }
      };
      socket.onclose = () => {
        lastEventAtRef.current = 0;
        if (active) retry = setTimeout(connect, 3000);
      };
      socket.onerror = () => socket.close();
    };
    connect();
    const watchdog = setInterval(() => {
      if (lastEventAtRef.current && needsDeviceFallback(lastEventAtRef.current, Date.now())) socket.close();
    }, 10000);
    return () => {
      active = false;
      clearInterval(watchdog);
      lastEventAtRef.current = 0;
      clearTimeout(retry);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (!form && !editing && !deleting) return;
    const origin = document.activeElement as HTMLElement | null;
    const targets = () => [
      ...(dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href],[tabindex="0"]',
      ) ?? []),
    ];
    targets()[0]?.focus();
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pendingRef.current) {
        setForm(null);
        setEditing(null);
        setDeleting(null);
      }
      if (event.key === "Tab") {
        const elements = targets();
        if (event.shiftKey && document.activeElement === elements[0]) {
          event.preventDefault();
          elements.at(-1)?.focus();
        } else if (
          !event.shiftKey &&
          document.activeElement === elements.at(-1)
        ) {
          event.preventDefault();
          elements[0]?.focus();
        }
      }
    };
    document.addEventListener("keydown", listener);
    return () => {
      document.removeEventListener("keydown", listener);
      origin?.focus();
    };
  }, [form, editing, deleting, providerSelected]);

  async function perform(action: () => Promise<unknown>, success = t("Saved")) {
    if (pendingRef.current) return false;
    pendingRef.current = true;
    setPending(true);
    setError(null);
    try {
      await action();
      notify("success", success);
      try {
        await load();
      } catch (reason) {
        setError(
          reason instanceof Error
            ? reason.message
            : t("Unable to refresh devices"),
        );
      }
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("Request failed"));
      return false;
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }

  async function saveDevice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    if (
      await perform(() =>
        api(`devices/${editing!.id}`, "PATCH", {
          name: values.get("name"),
          room_id: values.get("room_id") || null,
          enabled: values.get("enabled") === "on",
          kind_override: values.get('kind_override') || null,
        }),
      )
    )
      setEditing(null);
  }

  async function sendDevice(device: Device, control: Control, value: StateValue) {
    if (devicePendingRef.current.has(device.id)) return false;
    devicePendingRef.current.add(device.id);
    setDevicePending(new Set(devicePendingRef.current));
    try {
      const updated = await api(`devices/${device.id}/actions`, 'POST', { code: control.code, value }) as Device;
      setDevices(previous => previous.map(item => item.id === updated.id
        ? mergeDeviceSnapshots([item], [updated], new Set())[0] : item));
      return true;
    } catch (reason) {
      notify('error', reason instanceof Error ? reason.message : t('Request failed'));
      try {
        const updated = await api(`devices/${device.id}`) as Device;
        setDevices(previous => previous.map(item => item.id === device.id ? updated : item));
      } catch { /* The next automatic refresh will retry. */ }
      return false;
    } finally {
      devicePendingRef.current.delete(device.id);
      setDevicePending(new Set(devicePendingRef.current));
    }
  }

  const visible = devices.filter(
    (device) =>
      (!filter || device.integration_id === filter) &&
      `${device.name} ${device.area} ${device.kind} ${device.product_name}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const current = form && form !== "new" ? form : null;
  return (
    <div className="w-full max-w-6xl space-y-3">
      <header className="flex items-center justify-between gap-2 sm:gap-4">
        <h1 className="shrink-0 font-brand text-xl font-bold tracking-tight sm:text-2xl">{t("Devices")}</h1>
        <div className="flex min-w-0 gap-0.5 rounded-lg bg-neutral-900/70 p-1" role="tablist" aria-label={t("Devices sections")}>
          {(["devices", "rooms", "integrations"] as const).map((value, index, tabs) => (
            <button
              key={value}
              id={`devices-tab-${value}`}
              role="tab"
              aria-selected={tab === value}
              aria-controls={`devices-panel-${value}`}
              tabIndex={tab === value ? 0 : -1}
              onClick={() => setTab(value)}
              onKeyDown={(event) => {
                const next = event.key === "ArrowRight" ? (index + 1) % tabs.length
                  : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length
                  : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
                if (next !== null) {
                  event.preventDefault();
                  setTab(tabs[next]);
                  document.getElementById(`devices-tab-${tabs[next]}`)?.focus();
                }
              }}
              className={`rounded-md px-1.5 py-1.5 text-xs capitalize transition-colors sm:px-3 sm:text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${tab === value ? "bg-neutral-800 text-accent-muted" : "text-neutral-500 hover:text-neutral-200"}`}
            >{t(value === "devices" ? "Devices" : value === "rooms" ? "Rooms" : "Integrations")}</button>
          ))}
        </div>
      </header>
      <section id={`devices-panel-${tab}`} role="tabpanel" aria-labelledby={`devices-tab-${tab}`} className="space-y-3">
      {loading ? (
        <p role="status" className="py-6 text-neutral-500">{t("Loading devices…")}</p>
      ) : tab === "rooms" ? (
        <RoomsView
          rooms={rooms}
          devices={devices}
          admin={admin}
          pending={pending}
          devicePending={new Set([...devicePending, ...(pending && editing ? [editing.id] : [])])}
          api={api}
          perform={perform}
          editDevice={(device) => {
            setError(null);
            setEditing(device);
          }}
          send={sendDevice}
        />
      ) : tab === "integrations" ? (
        <div className="grid items-stretch gap-2 lg:grid-cols-2 xl:grid-cols-3">
          {integrations.map((home) => (
            <article
              key={home.id}
              className="flex min-w-0 items-center gap-2 rounded-lg bg-neutral-900/50 px-3 py-2"
            >
              <span className="inline-flex shrink-0 items-center gap-1">
                {home.provider === "tuya" ? <img src="/admin/brand/tuya.svg" alt="" className="h-7 w-7 shrink-0" /> : <PuzzlePiece size={28} className="shrink-0 text-neutral-400" />}
                <span className="text-sm font-semibold">{home.provider === "tuya" ? "tuya" : providerExtensions.find(provider => provider.id === home.provider)?.name ?? home.provider}</span>
              </span>
              <h2 className="min-w-0 flex-1 truncate text-sm" title={home.name}>
                {home.name}
              </h2>
              <span
                role="img"
                aria-label={home.error ? t("Error") : enumLabel(home.status)}
                title={home.error ? t("Error") : enumLabel(home.status)}
                className={`h-2 w-2 shrink-0 rounded-full ${home.status === "connected" ? "bg-accent" : "bg-red-400"}`}
              />
              {admin && (
                <>
                  <button
                    className={`${button} border-transparent px-2`}
                    disabled={pending}
                    aria-label={t("Configure {{name}}", { name: home.name })}
                    onClick={() => {
                      setError(null);
                      setProviderSelected(home.provider);
                      setForm(home);
                    }}
                  >
                    <SlidersHorizontal size={16} />
                  </button>
                  <button
                    className={`${button} border-transparent px-2 text-neutral-500`}
                    disabled={pending}
                    aria-label={t("Remove {{name}}", { name: home.name })}
                    onClick={() => setDeleting(home)}
                  >
                    <Trash size={16} />
                  </button>
                </>
              )}
            </article>
          ))}
          {admin ? (
            <button
              className="flex min-h-12 items-center gap-2 rounded-lg bg-accent/10 px-3 py-2 text-left text-sm font-medium text-accent-muted hover:bg-accent/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              onClick={() => {
                setError(null);
                setProviderSelected(null);
                setForm("new");
              }}
            >
              <Plus size={20} aria-hidden="true" />{t("Add integration")}</button>
          ) : !integrations.length ? (
            <p className="py-3 text-sm text-neutral-500">{t("No integrations")}</p>
          ) : null}
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <input
              type="search"
              aria-label={t("Search devices")}
              placeholder={t("Search devices…")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className={`${input} min-w-0 flex-1`}
            />
            <select
              aria-label={t("Filter by integration")}
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              title={integrations.find((home) => home.id === filter)?.name ?? "All integrations"}
              className={`${input} max-w-28 min-w-0 shrink-0 sm:max-w-40`}
            >
              <option value="">{t("All")}</option>
              {integrations.map((home) => (
                <option key={home.id} value={home.id}>
                  {home.name}
                </option>
              ))}
            </select>
          </div>
          {!visible.length ? (
            <div className="py-6 text-center">
              <Devices size={28} className="mx-auto text-neutral-600" />
              <h2 className="mt-2 text-sm text-neutral-500">
                {devices.length ? t("No matching devices") : t("No devices")}
              </h2>
            </div>
          ) : (
            <div className="device-card-list">
              {visible.map((device) => (
                <DeviceCard
                  key={device.id}
                  device={device}
                  pending={devicePending.has(device.id) || (pending && editing?.id === device.id)}
                  edit={() => {
                    setError(null);
                    setEditing(device);
                  }}
                  send={(control, value) => sendDevice(device, control, value)}
                />
              ))}
            </div>
          )}
        </>
      )}
      </section>
      {(form || editing || deleting) && (
        <div
          className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/75 p-4"
          onClick={(event) => {
            if (event.target === event.currentTarget && !pendingRef.current) {
              setForm(null);
              setEditing(null);
              setDeleting(null);
            }
          }}
        >
          <section
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="device-dialog-title"
            className="my-4 w-full max-w-lg space-y-4 rounded-lg border border-neutral-800 bg-neutral-950 p-4 shadow-2xl"
          >
            <div className="flex items-center justify-between">
              <h2
                id="device-dialog-title"
                className="font-brand text-xl font-semibold"
              >
                {form
                  ? providerSelected
                    ? providerSelected === "tuya" ? "Tuya" : selectedExtension?.name ?? providerSelected
                    : t("Add integration")
                  : editing
                    ? t("Device settings")
                    : t("Remove integration?")}
              </h2>
              <button
                className={button}
                disabled={pending}
                aria-label={t("Close dialog")}
                onClick={() => {
                  setForm(null);
                  setEditing(null);
                  setDeleting(null);
                }}
              >
                <X size={18} />
              </button>
            </div>
            {form ? (
              !providerSelected ? (
                <div className="space-y-2">
                  <button className={`${button} w-full justify-start`} onClick={() => setProviderSelected("tuya")}>
                    <img src="/admin/brand/tuya.svg" alt="" className="h-7 w-7" />Tuya
                  </button>
                  {providerExtensions.map(provider => <button key={provider.id} className={`${button} w-full justify-start`} onClick={() => setProviderSelected(provider.id)}>{provider.name ?? provider.id}</button>)}
                </div>
              ) : selectedExtension ? (
                <ProviderForm provider={selectedExtension} context={context} integration={current} back={() => setProviderSelected(null)} connected={() => { setForm(null); void load().catch((reason: Error) => notify("error", reason.message)); }} />
              ) : (
                <TuyaLogin
                  request={api}
                  integration={current}
                  back={() => setProviderSelected(null)}
                  connected={() => {
                    setForm(null);
                    void load().catch((reason) => setError(reason instanceof Error ? reason.message : t("Unable to refresh devices")));
                  }}
                />
              )
            ) : editing ? (
              <div className="space-y-4">
                {admin && (
                  <form
                    onSubmit={(event) => void saveDevice(event)}
                    className="space-y-3"
                  >
                    <label className="block space-y-1 text-sm">{t("Name")}<input
                        required
                        name="name"
                        maxLength={128}
                        defaultValue={editing.name}
                        className={input}
                      />
                    </label>
                    <label className="block space-y-1 text-sm">{t("Room")}<select
                        name="room_id"
                        aria-label={t("Room")}
                        defaultValue={editing.room_id ?? ""}
                        className={input}
                      >
                        <option value="">{t("Unassigned")}</option>
                        {rooms.map((room) => (
                          <option key={room.id} value={room.id}>
                            {room.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block space-y-1 text-sm">{t('Device type')}<select name="kind_override" defaultValue={editing.kind_override ?? ''} className={input}>
                      <option value="">{t('Automatic')}</option>
                      <option value="cz">{t('Socket')}</option>
                      <option value="dj">{t('Light')}</option>
                    </select></label>
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          name="enabled"
                          defaultChecked={editing.enabled}
                          className="accent-accent"
                        />{t("Enable control")}</label>
                      <button className={button} disabled={pending}>
                        {pending ? t("Saving…") : t("Save")}
                      </button>
                    </div>
                  </form>
                )}
                <div className="space-y-4 border-t border-neutral-800 pt-3">
                  <dl className="space-y-2">
                    {Object.keys(editing.state)
                      .filter(
                        (code) =>
                          !editing.controls.some(
                            (control) => control.code === code,
                          ),
                      )
                      .map((code) => {
                        const metric = deviceMetric(
                          devices.find((device) => device.id === editing.id) ??
                            editing,
                          code,
                        );
                        return (
                          metric && (
                            <div
                              key={code}
                              className="flex justify-between gap-3 text-sm"
                            >
                              <dt className="text-neutral-500">
                                {t(metric.label)}
                              </dt>
                              <dd className="text-right tabular-nums">
                                {metricText(metric)} {metric.unit}
                              </dd>
                            </div>
                          )
                        );
                      })}
                  </dl>
                  {editing.controls
                    .filter(
                      (control) =>
                        !editing.controls.some(
                          (c) => c.code === "switch_led",
                        ) ||
                        ![
                          "switch_led",
                          "bright_value",
                          "bright_value_v2",
                          "colour_data",
                          "colour_data_v2",
                          "work_mode",
                          "temp_value",
                          "temp_value_v2",
                          "color_scene",
                        ].includes(control.code),
                    )
                    .map((control) => (
                      <CompactControl
                        key={control.code}
                        control={control}
                        value={
                          devices.find((d) => d.id === editing.id)?.state[
                            control.code
                          ]
                        }
                        disabled={
                          devicePending.has(editing.id) || pending || !editing.available || !editing.enabled
                        }
                        send={(value) => sendDevice(editing, control, value)}
                      />
                    ))}
                </div>
              </div>
            ) : (
              <>
                <p className="text-sm text-neutral-400">
                  {t("Remove {{name}} and its imported devices from HDO? Devices stay in your provider account.", { name: deleting!.name })}
                </p>
                <button
                  className={`${button} w-full text-red-300`}
                  disabled={pending}
                  onClick={async () => {
                    if (
                      await perform(
                        () => api(`integrations/${deleting!.id}`, "DELETE"),
                        t("Integration removed"),
                      )
                    )
                      setDeleting(null);
                  }}
                >
                  {pending ? t("Removing…") : t("Remove integration")}
                </button>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
