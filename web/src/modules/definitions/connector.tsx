import { Plus } from "@phosphor-icons/react/Plus";
import { ArrowClockwise } from "@phosphor-icons/react/ArrowClockwise";
import { CaretDown } from "@phosphor-icons/react/CaretDown";
import { CheckCircle } from "@phosphor-icons/react/CheckCircle";
import { CircleNotch } from "@phosphor-icons/react/CircleNotch";
import { Lightbulb } from "@phosphor-icons/react/Lightbulb";
import { MagnifyingGlass } from "@phosphor-icons/react/MagnifyingGlass";
import { PlugsConnected } from "@phosphor-icons/react/PlugsConnected";
import { WarningCircle } from "@phosphor-icons/react/WarningCircle";
import { X } from "@phosphor-icons/react/X";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { registerModule, type PanelModuleContext, type PanelModuleProps } from "../registry";

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
  host: string | null;
  port: number | null;
  devices: LinkerDevice[];
};

type DiscoveryCandidate = {
  candidate_id: string;
  name: string;
  transport: string;
  requires_pairing: boolean;
};

type DiscoverySession = {
  status: "running" | "completed" | "failed";
  candidates: DiscoveryCandidate[];
  error: string | null;
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
  const [linkerHost, setLinkerHost] = useState("");
  const [linkerPort, setLinkerPort] = useState("");
  const [minisecret, setMinisecret] = useState("");
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

  useEffect(() => {
    if (!showAdd) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !actionPending) setShowAdd(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [showAdd, actionPending]);

  async function addLinker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionPending(true);
    setActionError(null);
    setSuccess(null);
    try {
      const response = await context.api.request("/api/v1/admin/linkers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ host: linkerHost, port: Number(linkerPort), minisecret }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const added = (await response.json()) as Linker;
      setLinkers((current) => [...current.filter((item) => item.id !== added.id), added].sort((left, right) => left.id.localeCompare(right.id)));
      setLinkerHost("");
      setLinkerPort("");
      setMinisecret("");
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
          {isAdmin && <button type="button" onClick={() => { setShowAdd(true); setActionError(null); }} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-semibold text-neutral-950 transition hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"><Plus size={17} aria-hidden="true" />Add linker</button>}
          <button
            type="button"
            onClick={() => void loadLinkers()}
            disabled={loadState === "loading"}
            aria-label="Refresh linkers"
            title="Refresh linkers"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-neutral-700 text-neutral-300 transition hover:border-neutral-500 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60"
          >
            <ArrowClockwise size={17} aria-hidden="true" />
          </button>
        </div>
      </div>

      {showAdd && isAdmin && <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !actionPending) setShowAdd(false); }}>
        <div role="dialog" aria-modal="true" aria-labelledby="add-linker-title" className="w-full max-w-lg rounded-lg border border-neutral-700 bg-neutral-950 p-5 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
          <div className="flex items-center justify-between gap-4">
            <h2 id="add-linker-title" className="font-brand text-xl font-bold text-neutral-100">Add linker</h2>
            <button type="button" aria-label="Close dialog" onClick={() => setShowAdd(false)} disabled={actionPending} className="grid h-9 w-9 place-items-center rounded-md text-neutral-400 transition hover:bg-neutral-800 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60"><X size={19} aria-hidden="true" /></button>
          </div>
          <form className="mt-5 grid gap-4" onSubmit={(event) => void addLinker(event)}>
            <label className="grid gap-2 text-sm text-neutral-300">
              IP address
              <input autoFocus required value={linkerHost} onChange={(event) => setLinkerHost(event.target.value)} className="h-10 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-neutral-100 outline-none transition focus:border-accent" />
            </label>
            <label className="grid gap-2 text-sm text-neutral-300">
              Port
              <input required type="number" min="1" max="65535" value={linkerPort} onChange={(event) => setLinkerPort(event.target.value)} className="h-10 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-neutral-100 outline-none transition focus:border-accent" />
            </label>
            <label className="grid gap-2 text-sm text-neutral-300">
              Minisecret
              <input required type="password" autoComplete="new-password" value={minisecret} onChange={(event) => setMinisecret(event.target.value)} className="h-10 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-neutral-100 outline-none transition focus:border-accent" />
            </label>
            {actionError && <StatusMessage tone="error" icon={<WarningCircle size={18} aria-hidden="true" />} message={actionError} />}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowAdd(false)} disabled={actionPending} className="h-10 rounded-md border border-neutral-700 px-4 text-sm text-neutral-300 transition hover:border-neutral-500 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60">Cancel</button>
              <button type="submit" disabled={actionPending} className="inline-flex h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-neutral-950 transition hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60">{actionPending && <CircleNotch className="animate-spin" size={17} aria-hidden="true" />}Add</button>
            </div>
          </form>
        </div>
      </div>}
      {success && <StatusMessage tone="success" icon={<CheckCircle size={18} aria-hidden="true" />} message={success} />}
      {loadState === "loading" && <StatusMessage icon={<CircleNotch className="animate-spin" size={18} />} message="Loading linkers" />}
      {loadState === "error" && (
        <div className="flex flex-wrap items-center justify-between gap-4 border-y border-red-900/70 py-4 text-sm text-red-300">
          <span className="inline-flex items-center gap-2"><WarningCircle size={18} aria-hidden="true" />{loadError}</span>
          <button type="button" onClick={() => void loadLinkers()} className="text-accent-muted underline underline-offset-4">Retry</button>
        </div>
      )}
      {loadState === "ready" && linkers.length === 0 && <StatusMessage icon={<PlugsConnected size={18} />} message="No linkers" />}
      {loadState === "ready" && linkers.length > 0 && <div className="divide-y divide-neutral-800 border-y border-neutral-800">{linkers.map((linker) => <LinkerGroup key={linker.id} linker={linker} api={context.api} />)}</div>}
    </div>
  );
}

function LinkerGroup({ linker, api }: { linker: Linker; api: PanelModuleContext["api"] }) {
  const [expanded, setExpanded] = useState(false);
  const [scanState, setScanState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [scanError, setScanError] = useState<string | null>(null);
  const [discovery, setDiscovery] = useState<DiscoverySession | null>(null);

  async function scan() {
    setExpanded(true);
    setScanState("loading");
    setScanError(null);
    setDiscovery(null);
    try {
      const response = await api.request("/api/v1/discovery/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ linker_id: linker.id, timeout_s: 5 }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const started = (await response.json()) as { session_id: string };
      for (let attempt = 0; attempt < 14; attempt += 1) {
        const result = await api.request(`/api/v1/discovery/sessions/${encodeURIComponent(started.session_id)}`);
        if (!result.ok) throw new Error(await readError(result));
        const session = (await result.json()) as DiscoverySession;
        if (session.status !== "running") {
          setDiscovery(session);
          setScanState(session.status === "completed" ? "ready" : "error");
          if (session.status === "failed") setScanError(session.error ?? "Discovery failed");
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      throw new Error("Discovery timed out");
    } catch (error) {
      setScanState("error");
      setScanError(error instanceof Error ? error.message : "Unable to scan");
    }
  }

  return (
    <article>
      <header className="flex items-center gap-3 px-3 py-3 min-[390px]:px-4">
        <button type="button" onClick={() => setExpanded((current) => !current)} aria-expanded={expanded} className="flex min-w-0 flex-1 items-center gap-3 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-accent/10 text-accent-muted"><PlugsConnected size={18} aria-hidden="true" /></span>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-neutral-100">{linker.name}</h2>
            <p className="truncate text-xs text-neutral-500">{linker.host && linker.port ? `${linker.host}:${linker.port}` : linker.id} · {linker.devices.length} {linker.devices.length === 1 ? "device" : "devices"}</p>
          </div>
          <CaretDown size={16} className={`ml-auto shrink-0 text-neutral-500 transition-transform ${expanded ? "rotate-180" : ""}`} aria-hidden="true" />
        </button>
        <span className={`hidden items-center gap-1.5 text-xs min-[390px]:inline-flex ${linker.available ? "text-accent-muted" : "text-neutral-500"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${linker.available ? "bg-accent-muted" : "bg-neutral-600"}`} />
          {linker.available ? "Available" : "Offline"}
        </span>
        <button type="button" onClick={() => void scan()} disabled={!linker.available || scanState === "loading"} aria-label={`Scan ${linker.name}`} title={linker.available ? "Scan for devices" : "Linker is offline"} className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-neutral-400 transition hover:bg-neutral-900 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-40">{scanState === "loading" ? <CircleNotch className="animate-spin" size={17} aria-hidden="true" /> : <MagnifyingGlass size={17} aria-hidden="true" />}</button>
      </header>

      {expanded && <section className="space-y-4 border-t border-neutral-800 px-3 py-3 min-[390px]:px-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-500">
          <span>Protocols <strong className="font-medium text-neutral-300">{linker.transports.length > 0 ? linker.transports.join(", ") : "—"}</strong></span>
          {linker.version && <span>Version <strong className="font-medium text-neutral-300">v{linker.version}</strong></span>}
        </div>
        {scanError && <StatusMessage tone="error" icon={<WarningCircle size={17} aria-hidden="true" />} message={scanError} />}
        {scanState === "ready" && discovery && <DiscoveryResult session={discovery} />}
        {linker.devices.length === 0 ? (
          <p className="text-sm text-neutral-500">No connected devices</p>
        ) : (
          <ul className="divide-y divide-neutral-800 border-y border-neutral-800">
            {linker.devices.map((device) => <DeviceRow key={device.light_id} device={device} />)}
          </ul>
        )}
      </section>}
    </article>
  );
}

function DiscoveryResult({ session }: { session: DiscoverySession }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-neutral-500"><CheckCircle size={15} className="text-accent-muted" aria-hidden="true" />Found {session.candidates.length}</div>
      {session.candidates.length > 0 && <ul className="divide-y divide-neutral-800 border-y border-neutral-800">
        {session.candidates.map((candidate) => <li key={candidate.candidate_id} className="flex items-center gap-3 py-2.5 text-sm">
          <Lightbulb size={18} className="shrink-0 text-accent-muted" aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate text-neutral-200">{candidate.name}</span>
          <span className="shrink-0 text-xs text-neutral-500">{candidate.requires_pairing ? "Pairing required" : candidate.transport}</span>
        </li>)}
      </ul>}
    </div>
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
