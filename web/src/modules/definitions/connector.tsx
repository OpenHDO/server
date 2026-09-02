import { Plus } from "@phosphor-icons/react/Plus";
import { ArrowClockwise } from "@phosphor-icons/react/ArrowClockwise";
import { CheckCircle } from "@phosphor-icons/react/CheckCircle";
import { CircleNotch } from "@phosphor-icons/react/CircleNotch";
import { Lightbulb } from "@phosphor-icons/react/Lightbulb";
import { PlugsConnected } from "@phosphor-icons/react/PlugsConnected";
import { WarningCircle } from "@phosphor-icons/react/WarningCircle";
import { XCircle } from "@phosphor-icons/react/XCircle";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { registerModule, type PanelModuleProps } from "../registry";

type LinkerDevice = {
  light_id: string;
  name: string;
  capability: {
    color_modes?: string[] | null;
  };
};

type Linker = {
  id: string;
  name: string;
  version: string | null;
  transports: string[];
  available: boolean;
  devices: LinkerDevice[];
};

type RequestError = { detail?: string };

async function readError(response: Response) {
  const payload = (await response.json().catch(() => null)) as RequestError | null;
  return payload?.detail ?? `Request failed (${response.status})`;
}

function ConnectorModule({ context }: PanelModuleProps) {
  const [linkers, setLinkers] = useState<Linker[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [linkerId, setLinkerId] = useState("");
  const [linkerName, setLinkerName] = useState("");
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const isAdmin = context.auth.user?.role === "admin";

  async function loadLinkers() {
    setLoadState("loading");
    setLoadError(null);
    try {
      const response = await context.api.request("/api/v1/linkers");
      if (!response.ok) throw new Error(await readError(response));
      const payload = (await response.json()) as { linkers: Linker[] };
      setLinkers(payload.linkers);
      setLoadState("ready");
    } catch (error) {
      setLoadState("error");
      setLoadError(error instanceof Error ? error.message : "Unable to load linkers");
    }
  }

  useEffect(() => {
    void loadLinkers();
  }, []);

  async function addLinker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionPending(true);
    setActionError(null);
    setSuccess(null);
    try {
      const response = await context.api.request("/api/v1/admin/linkers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: linkerId, name: linkerName }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const added = (await response.json()) as Linker;
      setLinkers((current) => [...current.filter((item) => item.id !== added.id), added].sort((left, right) => left.id.localeCompare(right.id)));
      setLinkerId("");
      setLinkerName("");
      setShowAdd(false);
      setSuccess("Linker added");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to add linker");
    } finally {
      setActionPending(false);
    }
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-brand text-2xl font-bold tracking-tight">Linkers</h1>
        <div className="flex flex-wrap gap-2">
          {isAdmin && <button type="button" onClick={() => { setShowAdd((current) => !current); setActionError(null); }} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-semibold text-neutral-950 transition hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"><Plus size={17} aria-hidden="true" />Add linker</button>}
          <button
            type="button"
            onClick={() => void loadLinkers()}
            disabled={loadState === "loading"}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-neutral-700 px-3 text-sm text-neutral-300 transition hover:border-neutral-500 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60"
          >
            <ArrowClockwise size={17} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </div>

      {showAdd && isAdmin && <form className="grid gap-4 border-y border-neutral-800 py-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end" onSubmit={(event) => void addLinker(event)}>
        <label className="grid gap-2 text-sm text-neutral-300">
          Linker ID
          <input required pattern="[a-z][a-z0-9._-]{1,63}" value={linkerId} onChange={(event) => setLinkerId(event.target.value)} className="h-10 rounded-md border border-neutral-700 bg-neutral-950 px-3 text-neutral-100 outline-none transition focus:border-accent" />
        </label>
        <label className="grid gap-2 text-sm text-neutral-300">
          Name
          <input required value={linkerName} onChange={(event) => setLinkerName(event.target.value)} className="h-10 rounded-md border border-neutral-700 bg-neutral-950 px-3 text-neutral-100 outline-none transition focus:border-accent" />
        </label>
        <div className="flex gap-2 md:pb-0">
          <button type="submit" disabled={actionPending} className="inline-flex h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-neutral-950 transition hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60">{actionPending && <CircleNotch className="animate-spin" size={17} aria-hidden="true" />}Add</button>
          <button type="button" onClick={() => setShowAdd(false)} className="h-10 rounded-md border border-neutral-700 px-4 text-sm text-neutral-300 transition hover:border-neutral-500 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">Cancel</button>
        </div>
      </form>}
      {actionError && <StatusMessage tone="error" icon={<WarningCircle size={18} aria-hidden="true" />} message={actionError} />}
      {success && <StatusMessage tone="success" icon={<CheckCircle size={18} aria-hidden="true" />} message={success} />}
      {loadState === "loading" && <StatusMessage icon={<CircleNotch className="animate-spin" size={18} />} message="Loading linkers" />}
      {loadState === "error" && (
        <div className="flex flex-wrap items-center justify-between gap-4 border-y border-red-900/70 py-4 text-sm text-red-300">
          <span className="inline-flex items-center gap-2"><WarningCircle size={18} aria-hidden="true" />{loadError}</span>
          <button type="button" onClick={() => void loadLinkers()} className="text-accent-muted underline underline-offset-4">Retry</button>
        </div>
      )}
      {loadState === "ready" && linkers.length === 0 && <StatusMessage icon={<PlugsConnected size={18} />} message="No linkers" />}
      {loadState === "ready" && linkers.length > 0 && <div className="space-y-4">{linkers.map((linker) => <LinkerGroup key={linker.id} linker={linker} />)}</div>}
    </div>
  );
}

function LinkerGroup({ linker }: { linker: Linker }) {
  return (
    <article className="overflow-hidden rounded-lg border border-neutral-800 bg-neutral-950/60">
      <header className="flex flex-wrap items-start justify-between gap-4 p-4 min-[390px]:p-5">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-accent/10 text-accent-muted"><PlugsConnected size={21} aria-hidden="true" /></span>
          <div className="min-w-0">
            <h2 className="truncate font-brand text-lg font-bold text-neutral-100">{linker.name}</h2>
            <p className="truncate text-sm text-neutral-500">{linker.id} · {linker.version ? `v${linker.version}` : "not registered"}</p>
          </div>
        </div>
        <span className={`inline-flex items-center gap-2 text-sm ${linker.available ? "text-accent-muted" : "text-neutral-500"}`}>
          {linker.available ? <CheckCircle size={18} aria-hidden="true" /> : <XCircle size={18} aria-hidden="true" />}
          {linker.available ? "Available" : "Unavailable"}
        </span>
      </header>

      <div className="grid gap-4 border-t border-neutral-800 px-4 py-4 min-[390px]:grid-cols-2 min-[390px]:px-5 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div>
          <p className="text-xs uppercase tracking-wide text-neutral-500">Protocols</p>
          <p className="mt-1 break-words text-sm text-neutral-200">{linker.transports.length > 0 ? linker.transports.join(", ") : "None"}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-neutral-500">Devices</p>
          <p className="mt-1 text-sm text-neutral-200">{linker.devices.length}</p>
        </div>
      </div>

      <section className="border-t border-neutral-800">
        {linker.devices.length === 0 ? (
          <p className="px-4 py-5 text-sm text-neutral-500 min-[390px]:px-5">No devices</p>
        ) : (
          <ul className="divide-y divide-neutral-800">
            {linker.devices.map((device) => <DeviceRow key={device.light_id} device={device} />)}
          </ul>
        )}
      </section>
    </article>
  );
}

function DeviceRow({ device }: { device: LinkerDevice }) {
  return (
    <li className="flex items-center gap-3 px-4 py-4 min-[390px]:px-5">
      <Lightbulb size={20} className="shrink-0 text-accent-muted" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-neutral-100">{device.name}</p>
        <p className="truncate text-xs text-neutral-500">{device.light_id}</p>
      </div>
      <span className="shrink-0 text-xs uppercase tracking-wide text-neutral-500">{device.capability.color_modes?.join("/") ?? "Light"}</span>
    </li>
  );
}

function StatusMessage({ icon, message, tone = "neutral" }: { icon: ReactNode; message: string; tone?: "neutral" | "error" | "success" }) {
  const color = tone === "error" ? "text-red-300" : tone === "success" ? "text-accent-muted" : "text-neutral-500";
  return <div className={`flex items-center gap-2 border-y border-neutral-800 py-4 text-sm ${color}`}>{icon}{message}</div>;
}

registerModule({
  id: "connector",
  label: "Connector",
  icon: PlugsConnected,
  order: 30,
  component: ConnectorModule,
});
