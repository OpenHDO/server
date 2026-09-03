import { Plus } from "@phosphor-icons/react/Plus";
import { ArrowClockwise } from "@phosphor-icons/react/ArrowClockwise";
import { ArrowLeft } from "@phosphor-icons/react/ArrowLeft";
import { CaretDown } from "@phosphor-icons/react/CaretDown";
import { CheckCircle } from "@phosphor-icons/react/CheckCircle";
import { CircleNotch } from "@phosphor-icons/react/CircleNotch";
import { DotsThreeVertical } from "@phosphor-icons/react/DotsThreeVertical";
import { Lightbulb } from "@phosphor-icons/react/Lightbulb";
import { MagnifyingGlass } from "@phosphor-icons/react/MagnifyingGlass";
import { PencilSimple } from "@phosphor-icons/react/PencilSimple";
import { Power } from "@phosphor-icons/react/Power";
import { PlugsConnected } from "@phosphor-icons/react/PlugsConnected";
import { Trash } from "@phosphor-icons/react/Trash";
import { WarningCircle } from "@phosphor-icons/react/WarningCircle";
import { WifiHigh } from "@phosphor-icons/react/WifiHigh";
import { X } from "@phosphor-icons/react/X";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { registerModule, type PanelModuleContext, type PanelModuleProps } from "../registry";

type RgbColor = {
  r: number;
  g: number;
  b: number;
};

type BulbState = {
  power: boolean;
  brightness: number;
  rgb_color: RgbColor;
  state_revision: number;
};

type Bulb = {
  id: string;
  name: string;
  capability: {
    power: boolean;
    brightness: { min: number; max: number };
    color_modes?: string[] | null;
  };
  state: BulbState | null;
};

type Linker = {
  id: string;
  name: string;
  version: string | null;
  transports: string[];
  available: boolean;
  host: string | null;
  port: number | null;
  bulbs: Bulb[];
};

type ApiBulb = Omit<Bulb, "id"> & { light_id: string };
type ApiLinker = Omit<Linker, "bulbs"> & { devices: ApiBulb[] };

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

const protocolIcons: Record<string, string> = {
  bluetooth: "/admin/brand/protocols/bluetooth.svg",
  zigbee: "/admin/brand/protocols/zigbee.svg",
  matter: "/admin/brand/protocols/matter.svg",
};

type RequestError = { detail?: string };

async function readError(response: Response) {
  const payload = (await response.json().catch(() => null)) as RequestError | null;
  return payload?.detail ?? `Request failed (${response.status})`;
}

function normalizeLinkers(payload: { linkers: ApiLinker[] }): Linker[] {
  return payload.linkers.map(({ devices, ...linker }) => ({
    ...linker,
    bulbs: devices.map(({ light_id, ...bulb }) => ({ id: light_id, ...bulb })),
  }));
}

function TransportIcon({ transport }: { transport: string }) {
  if (transport === "wifi") return <WifiHigh size={16} aria-hidden="true" />;
  const asset = protocolIcons[transport];
  if (!asset) return <PlugsConnected size={16} aria-hidden="true" />;
  return <span aria-hidden="true" className="block h-4 w-4 bg-current [mask-position:center] [mask-repeat:no-repeat] [mask-size:contain]" style={{ maskImage: `url("${asset}")`, WebkitMaskImage: `url("${asset}")` }} />;
}

function ConnectorModule({ context }: PanelModuleProps) {
  const [linkers, setLinkers] = useState<Linker[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [linkerHost, setLinkerHost] = useState("");
  const [linkerPort, setLinkerPort] = useState("");
  const [secret, setSecret] = useState("");
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
      const payload = (await response.json()) as { linkers: ApiLinker[] };
      setLinkers(normalizeLinkers(payload));
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
        body: JSON.stringify({ host: linkerHost, port: Number(linkerPort), secret }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const addedPayload = (await response.json()) as ApiLinker;
      const added = normalizeLinkers({ linkers: [addedPayload] })[0];
      setLinkers((current) => [...current.filter((item) => item.id !== added.id), added].sort((left, right) => left.id.localeCompare(right.id)));
      setLinkerHost("");
      setLinkerPort("");
      setSecret("");
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
              Secret
              <input required type="password" autoComplete="new-password" value={secret} onChange={(event) => setSecret(event.target.value)} className="h-10 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-neutral-100 outline-none transition focus:border-accent" />
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
      {loadState === "ready" && linkers.length > 0 && <div className="divide-y divide-neutral-800 border-y border-neutral-800">{linkers.map((linker) => <LinkerGroup key={linker.id} linker={linker} api={context.api} canManage={isAdmin} onRefresh={() => void loadLinkers()} />)}</div>}
    </div>
  );
}

function LinkerGroup({ linker, api, canManage, onRefresh }: { linker: Linker; api: PanelModuleContext["api"]; canManage: boolean; onRefresh: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [action, setAction] = useState<"rename" | "delete" | null>(null);
  const [actionName, setActionName] = useState(linker.name);
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen && !action) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !actionPending) {
        setMenuOpen(false);
        setAction(null);
      }
    };
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.removeEventListener("mousedown", closeOnOutsideClick);
    };
  }, [action, actionPending, menuOpen]);

  function openAction(next: "rename" | "delete") {
    setMenuOpen(false);
    setActionError(null);
    setActionName(linker.name);
    setAction(next);
  }

  async function renameLinker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionPending(true);
    setActionError(null);
    try {
      const response = await api.request(`/api/v1/admin/linkers/${encodeURIComponent(linker.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: actionName }),
      });
      if (!response.ok) throw new Error(await readError(response));
      setAction(null);
      onRefresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to rename linker");
    } finally {
      setActionPending(false);
    }
  }

  async function deleteLinker() {
    setActionPending(true);
    setActionError(null);
    try {
      const response = await api.request(`/api/v1/admin/linkers/${encodeURIComponent(linker.id)}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await readError(response));
      setAction(null);
      onRefresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to delete linker");
    } finally {
      setActionPending(false);
    }
  }

  return (
    <>
      <article>
      <header className="flex items-center gap-3 px-3 py-3 min-[390px]:px-4">
        <button type="button" onClick={() => setExpanded((current) => !current)} aria-expanded={expanded} className="flex min-w-0 flex-1 items-center gap-3 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-neutral-100">{linker.name}</h2>
            <p className="truncate text-xs text-neutral-500">{linker.host && linker.port ? `${linker.host}:${linker.port}` : linker.id} · {linker.bulbs.length} {linker.bulbs.length === 1 ? "bulb" : "bulbs"}</p>
          </div>
          <CaretDown size={16} className={`ml-auto shrink-0 text-neutral-300 transition-transform ${expanded ? "rotate-180" : ""}`} aria-hidden="true" />
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <div className="flex items-center gap-1 px-1 text-neutral-300">
            <span className={`grid h-8 w-8 place-items-center ${linker.available ? "text-accent-muted" : "text-red-400"}`} role="img" aria-label={linker.available ? "Linker available" : "Linker offline"} title={linker.available ? "Available" : "Offline"}><WifiHigh size={18} aria-hidden="true" /></span>
            {["bluetooth", "zigbee", "matter"].map((transport) => <span key={transport} className="grid h-8 w-8 place-items-center text-red-400" title={transport} aria-label={transport}><TransportIcon transport={transport} /></span>)}
          </div>
          {canManage && <div className="relative" ref={menuRef}>
            <button type="button" onClick={() => setMenuOpen((current) => !current)} aria-label={`Actions for ${linker.name}`} aria-expanded={menuOpen} aria-haspopup="menu" className="grid h-8 w-8 place-items-center rounded-md text-neutral-300 transition hover:bg-neutral-900 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"><DotsThreeVertical size={18} aria-hidden="true" /></button>
            {menuOpen && <div role="menu" className="absolute right-0 top-10 z-20 min-w-44 rounded-md border border-neutral-800 bg-neutral-950 p-1 shadow-2xl">
                <button type="button" role="menuitem" onClick={() => openAction("rename")} className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-neutral-300 transition hover:bg-neutral-900 hover:text-neutral-100"><PencilSimple size={17} aria-hidden="true" />Rename</button>
                <button type="button" role="menuitem" onClick={() => openAction("delete")} className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-red-300 transition hover:bg-red-950/50 hover:text-red-200"><Trash size={17} aria-hidden="true" />Delete</button>
              </div>}
          </div>}
        </div>
      </header>

      {expanded && <section className="space-y-4 border-t border-neutral-800 px-3 py-3 min-[390px]:px-4">
        <div className="grid grid-cols-1 gap-3 min-[600px]:grid-cols-2 min-[768px]:grid-cols-3 wide:grid-cols-4">
          <button type="button" onClick={() => setShowAddDevice(true)} className="flex min-h-64 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-neutral-700 text-neutral-400 transition hover:border-accent hover:text-accent-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-neutral-900"><Plus size={22} aria-hidden="true" /></span>
            <span className="text-sm font-medium">Add device</span>
          </button>
          {linker.bulbs.map((bulb) => <BulbCard key={bulb.id} bulb={bulb} api={api} />)}
        </div>
      </section>}
      </article>
      {action && <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !actionPending) setAction(null); }}>
        <div role="dialog" aria-modal="true" aria-labelledby="linker-action-title" className="w-full max-w-sm rounded-lg border border-neutral-700 bg-neutral-950 p-5 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
          <div className="flex items-center justify-between gap-4">
            <h2 id="linker-action-title" className="font-brand text-lg font-bold text-neutral-100">{action === "rename" ? "Rename linker" : "Delete linker"}</h2>
            <button type="button" aria-label="Close dialog" onClick={() => setAction(null)} disabled={actionPending} className="grid h-8 w-8 place-items-center rounded-md text-neutral-400 transition hover:bg-neutral-800 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60"><X size={18} aria-hidden="true" /></button>
          </div>
          {action === "rename" ? <form className="mt-4 grid gap-4" onSubmit={(event) => void renameLinker(event)}>
            <label className="grid gap-2 text-sm text-neutral-300">Name<input autoFocus required maxLength={128} value={actionName} onChange={(event) => setActionName(event.target.value)} className="h-10 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-neutral-100 outline-none transition focus:border-accent" /></label>
            {actionError && <StatusMessage tone="error" icon={<WarningCircle size={17} aria-hidden="true" />} message={actionError} />}
            <div className="flex justify-end gap-2"><button type="button" onClick={() => setAction(null)} disabled={actionPending} className="h-10 rounded-md border border-neutral-700 px-4 text-sm text-neutral-300 transition hover:border-neutral-500 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-60">Cancel</button><button type="submit" disabled={actionPending} className="inline-flex h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-neutral-950 transition hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-60">{actionPending && <CircleNotch className="animate-spin" size={17} aria-hidden="true" />}Save</button></div>
          </form> : <div className="mt-4 grid gap-4"><p className="text-sm text-neutral-400">Delete <span className="text-neutral-100">{linker.name}</span> and its connected devices?</p>{actionError && <StatusMessage tone="error" icon={<WarningCircle size={17} aria-hidden="true" />} message={actionError} />}<div className="flex justify-end gap-2"><button type="button" onClick={() => setAction(null)} disabled={actionPending} className="h-10 rounded-md border border-neutral-700 px-4 text-sm text-neutral-300 transition hover:border-neutral-500 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-60">Cancel</button><button type="button" onClick={() => void deleteLinker()} disabled={actionPending} className="inline-flex h-10 items-center gap-2 rounded-md bg-red-700 px-4 text-sm font-semibold text-white transition hover:bg-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400 disabled:opacity-60">{actionPending && <CircleNotch className="animate-spin" size={17} aria-hidden="true" />}Delete</button></div></div>}
        </div>
      </div>}
      {showAddDevice && <AddDeviceDialog api={api} linkerId={linker.id} available={linker.available} onClose={() => setShowAddDevice(false)} onPaired={onRefresh} />}
    </>
  );
}

function AddDeviceDialog({ api, linkerId, available, onClose, onPaired }: { api: PanelModuleContext["api"]; linkerId: string; available: boolean; onClose: () => void; onPaired: () => void }) {
  const [category, setCategory] = useState<"bulb" | null>(null);
  const [searchState, setSearchState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [searchError, setSearchError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<DiscoveryCandidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<string | null>(null);
  const [discoverySessionId, setDiscoverySessionId] = useState<string | null>(null);
  const [pairingState, setPairingState] = useState<"idle" | "loading" | "error">("idle");
  const [pairingError, setPairingError] = useState<string | null>(null);
  const busy = searchState === "loading" || pairingState === "loading";

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [busy, onClose]);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!available) {
      setSearchState("error");
      setSearchError("Linker is offline");
      return;
    }
    setSearchState("loading");
    setSearchError(null);
    setCandidates([]);
    setSelectedCandidate(null);
    setDiscoverySessionId(null);
    setPairingState("idle");
    setPairingError(null);
    try {
      const response = await api.request("/api/v1/discovery/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ linker_id: linkerId, timeout_s: 5 }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const started = (await response.json()) as { session_id: string };
      setDiscoverySessionId(started.session_id);
      for (let attempt = 0; attempt < 14; attempt += 1) {
        const result = await api.request(`/api/v1/discovery/sessions/${encodeURIComponent(started.session_id)}`);
        if (!result.ok) throw new Error(await readError(result));
        const session = (await result.json()) as DiscoverySession;
        if (session.status !== "running") {
          setCandidates(session.candidates);
          setSearchState(session.status === "completed" ? "ready" : "error");
          if (session.status === "failed") setSearchError(session.error ?? "Unable to find devices");
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      throw new Error("Search timed out");
    } catch (error) {
      setSearchState("error");
      setSearchError(error instanceof Error ? error.message : "Unable to find devices");
    }
  }

  async function pair() {
    if (!selectedCandidate || !discoverySessionId) return;
    setPairingState("loading");
    setPairingError(null);
    try {
      const response = await api.request("/api/v1/pairing/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ linker_id: linkerId, discovery_session_id: discoverySessionId, candidate_id: selectedCandidate, timeout_s: 30 }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const started = (await response.json()) as { session_id: string };
      for (let attempt = 0; attempt < 62; attempt += 1) {
        const result = await api.request(`/api/v1/pairing/sessions/${encodeURIComponent(started.session_id)}`);
        if (!result.ok) throw new Error(await readError(result));
        const session = (await result.json()) as { status: "running" | "completed" | "failed"; error: string | null };
        if (session.status !== "running") {
          if (session.status === "completed") {
            onPaired();
            onClose();
            return;
          }
          throw new Error(session.error ?? "Unable to pair device");
        }
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      throw new Error("Pairing timed out");
    } catch (error) {
      setPairingState("error");
      setPairingError(error instanceof Error ? error.message : "Unable to pair device");
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="add-device-title" className="w-full max-w-lg rounded-lg border border-neutral-700 bg-neutral-950 p-5 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-2">
            {category && <button type="button" aria-label="Back to device types" onClick={() => setCategory(null)} disabled={busy} className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-neutral-400 transition hover:bg-neutral-800 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-60"><ArrowLeft size={18} aria-hidden="true" /></button>}
            <h2 id="add-device-title" className="font-brand text-xl font-bold text-neutral-100">Add device</h2>
          </div>
          <button type="button" aria-label="Close dialog" onClick={onClose} disabled={busy} className="grid h-9 w-9 place-items-center rounded-md text-neutral-400 transition hover:bg-neutral-800 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60"><X size={19} aria-hidden="true" /></button>
        </div>
        {!category ? <div className="mt-5 grid grid-cols-2 gap-3">
          <button type="button" onClick={() => setCategory("bulb")} className="flex aspect-square flex-col items-center justify-center gap-3 rounded-lg border border-neutral-800 bg-neutral-900 p-4 text-neutral-200 transition hover:border-accent hover:bg-neutral-900/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
            <img src="/admin/devices/bulb.png" alt="" className="h-24 w-24 object-contain" />
            <span className="font-medium">Bulb</span>
          </button>
        </div> : <div className="mt-5 grid gap-4">
          {searchError && <StatusMessage tone="error" icon={<WarningCircle size={18} aria-hidden="true" />} message={searchError} />}
          {searchState === "idle" && <p className="text-sm text-neutral-500">Find a bulb on the Linker network.</p>}
          {searchState === "ready" && candidates.length === 0 && <StatusMessage icon={<Lightbulb size={18} />} message="No bulbs found" />}
          {candidates.length > 0 && <div className="grid gap-2">
            {candidates.map((candidate) => <button key={candidate.candidate_id} type="button" aria-pressed={selectedCandidate === candidate.candidate_id} onClick={() => setSelectedCandidate(candidate.candidate_id)} className={`flex items-center gap-3 rounded-md border p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${selectedCandidate === candidate.candidate_id ? "border-accent bg-accent/10" : "border-neutral-800 hover:border-accent"}`}>
              <img src="/admin/devices/bulb.png" alt="" className="h-12 w-12 shrink-0 object-contain" />
              <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-neutral-100">{candidate.name}</span><span className="block truncate text-xs text-neutral-500">{candidate.candidate_id}</span></span>
              {selectedCandidate === candidate.candidate_id && <CheckCircle className="shrink-0 text-accent-muted" weight="fill" size={19} aria-hidden="true" />}
            </button>)}
          </div>}
          {pairingError && <StatusMessage tone="error" icon={<WarningCircle size={18} aria-hidden="true" />} message={pairingError} />}
          <div className="flex items-center justify-between gap-3 border-t border-neutral-800 pt-4">
            <form onSubmit={(event) => void search(event)}>
              <button type="submit" disabled={busy} className="inline-flex h-10 shrink-0 items-center gap-2 rounded-md bg-accent px-3 text-sm font-semibold text-neutral-950 transition hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60">{searchState === "loading" ? <CircleNotch className="animate-spin" size={17} aria-hidden="true" /> : <MagnifyingGlass size={17} aria-hidden="true" />}Find</button>
            </form>
            {candidates.length > 0 && <button type="button" onClick={() => void pair()} disabled={!selectedCandidate || !discoverySessionId || busy} className="inline-flex h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-neutral-950 transition hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60">{pairingState === "loading" && <CircleNotch className="animate-spin" size={17} aria-hidden="true" />}{pairingState === "error" ? "Try again" : "Continue"}</button>}
          </div>
        </div>}
      </div>
    </div>
  );
}

function BulbCard({ bulb, api }: { bulb: Bulb; api: PanelModuleContext["api"] }) {
  const [state, setState] = useState<BulbState>(bulb.state ?? { power: false, brightness: bulb.capability.brightness.max, rgb_color: { r: 255, g: 255, b: 255 }, state_revision: 0 });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (bulb.state) setState(bulb.state);
  }, [bulb.id, bulb.state]);

  async function updateBulb(change: Partial<Pick<BulbState, "power" | "brightness" | "rgb_color">>) {
    const previous = state;
    setState((current) => ({ ...current, ...change }));
    setPending(true);
    setError(null);
    try {
      const response = await api.request(`/api/v1/lights/${encodeURIComponent(bulb.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...change, idempotency_key: crypto.randomUUID() }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const result = (await response.json()) as { payload?: { state?: BulbState | null } };
      if (result.payload?.state) setState(result.payload.state);
    } catch (updateError) {
      setState(previous);
      setError(updateError instanceof Error ? updateError.message : "Unable to control bulb");
    } finally {
      setPending(false);
    }
  }

  const color = `#${[state.rgb_color.r, state.rgb_color.g, state.rgb_color.b].map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;

  return (
    <article className="flex min-h-64 min-w-0 flex-col rounded-lg border border-neutral-800 bg-neutral-950 p-3">
      <div className="flex items-start justify-between gap-2">
        <span className={`text-xs ${state.power ? "text-accent-muted" : "text-neutral-500"}`}>{state.power ? "On" : "Off"}</span>
        <button type="button" aria-label={state.power ? `Turn off ${bulb.name}` : `Turn on ${bulb.name}`} onClick={() => void updateBulb({ power: !state.power })} disabled={pending || !bulb.capability.power} className={`grid h-8 w-8 place-items-center rounded-md transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-50 ${state.power ? "bg-accent text-neutral-950" : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"}`}>
          {pending ? <CircleNotch className="animate-spin" size={17} aria-hidden="true" /> : <Power size={17} aria-hidden="true" />}
        </button>
      </div>
      <div className="grid min-h-0 flex-1 place-items-center p-2">
        <img src="/admin/devices/bulb.png" alt="Bulb" className="h-full max-h-36 w-full object-contain" />
      </div>
      <div className="min-w-0 border-t border-neutral-800 pt-3">
        <p className="truncate text-sm font-medium text-neutral-100">{bulb.name}</p>
        <div className="mt-3 grid gap-2">
          <label className="grid gap-1 text-xs text-neutral-500">Brightness<input type="range" min={bulb.capability.brightness.min} max={bulb.capability.brightness.max} value={state.brightness} disabled={pending} onChange={(event) => setState((current) => ({ ...current, brightness: Number(event.currentTarget.value) }))} onPointerUp={(event) => void updateBulb({ brightness: Number(event.currentTarget.value) })} onKeyUp={(event) => { if (event.key.startsWith("Arrow") || event.key === "Home" || event.key === "End") void updateBulb({ brightness: Number(event.currentTarget.value) }); }} className="w-full accent-accent" /></label>
          {bulb.capability.color_modes?.length ? <label className="flex items-center justify-between gap-2 text-xs text-neutral-500">Color<input type="color" value={color} disabled={pending} onChange={(event) => { const value = event.currentTarget.value.slice(1); void updateBulb({ rgb_color: { r: Number.parseInt(value.slice(0, 2), 16), g: Number.parseInt(value.slice(2, 4), 16), b: Number.parseInt(value.slice(4, 6), 16) } }); }} className="h-7 w-10 cursor-pointer rounded border-0 bg-transparent p-0" /></label> : null}
        </div>
        {error && <p className="mt-2 truncate text-xs text-red-300" title={error}>{error}</p>}
      </div>
    </article>
  );
}

function StatusMessage({ icon, message, tone = "neutral" }: { icon: ReactNode; message: string; tone?: "neutral" | "error" | "success" }) {
  const color = tone === "error" ? "text-red-300" : tone === "success" ? "text-accent-muted" : "text-neutral-500";
  return <div className={`flex items-center gap-2 py-4 text-sm ${tone === "error" ? "" : "border-y border-neutral-800"} ${color}`}>{icon}{message}</div>;
}

registerModule({
  id: "connector",
  label: "Connector",
  icon: PlugsConnected,
  order: 30,
  component: ConnectorModule,
});
