import { useEffect, useState } from "react";
import {
  Activity,
  Boxes,
  Cable,
  ChevronRight,
  Clock3,
  CircleAlert,
  CircleCheck,
  Gauge,
  LayoutDashboard,
  Network,
  RefreshCw,
  Search,
  Server,
  Settings,
} from "lucide-react";
import { Button } from "./components/ui/button";

type Health = {
  api_version: number;
  runtime: string;
  instance_name: string;
  linkers_connected: number;
};

type Light = {
  light_id: string;
  name: string;
  linker_id: string;
  capability: {
    brightness: { min: number; max: number };
    color_modes?: string[] | null;
  };
  state?: {
    power: boolean;
    brightness: number;
    rgb_color: { r: number; g: number; b: number };
    state_revision: number;
  } | null;
};

type DiscoveryCandidate = {
  session_id: string;
  candidate_id: string;
  name: string;
  transport: "wifi";
  capabilities: Light["capability"][];
  requires_pairing: boolean;
};

type DiscoverySession = {
  session_id: string;
  linker_id: string;
  status: "running" | "completed" | "failed";
  candidates: DiscoveryCandidate[];
  error: string | null;
};

const ADMIN_TOKEN_STORAGE_KEY = "openhdo.admin.bearer";

function readAdminToken() {
  try {
    return window.sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveAdminToken(token: string) {
  try {
    if (token) window.sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
    else window.sessionStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
  } catch {
    // The API still reports the auth error if storage is unavailable.
  }
}

function apiFetch(path: string, token: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  if (token.trim()) headers.set("Authorization", `Bearer ${token.trim()}`);
  return fetch(path, { ...init, headers });
}

const navigation = [
  { label: "Overview", icon: LayoutDashboard },
  { label: "Lights", icon: Boxes },
  { label: "Linkers", icon: Cable },
  { label: "Settings", icon: Settings },
];

const DEFAULT_LINKER_ID = "openhdo.linker.rgb";

export default function App() {
  const [active, setActive] = useState("Overview");
  const [health, setHealth] = useState<Health | null>(null);
  const [lights, setLights] = useState<Light[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [linkerId, setLinkerId] = useState(DEFAULT_LINKER_ID);
  const [timeoutSeconds, setTimeoutSeconds] = useState(30);
  const [discoverySession, setDiscoverySession] = useState<DiscoverySession | null>(null);
  const [discoveryStarting, setDiscoveryStarting] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [adminToken, setAdminToken] = useState(readAdminToken);

  function updateAdminToken(token: string) {
    setAdminToken(token);
    saveAdminToken(token);
  }

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [healthResponse, lightsResponse] = await Promise.all([
        apiFetch("/api/v1/health", adminToken),
        apiFetch("/api/v1/lights", adminToken),
      ]);
      if (!healthResponse.ok || !lightsResponse.ok) {
        throw new Error("The server API did not authorize or return the admin data.");
      }
      const nextHealth = (await healthResponse.json()) as Health;
      const nextLights = (await lightsResponse.json()) as { lights: Light[] };
      setHealth(nextHealth);
      setLights(nextLights.lights);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The server admin data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    if (!discoverySession || discoverySession.status !== "running") return;
    let cancelled = false;
    const poll = async () => {
      try {
        const response = await apiFetch(`/api/v1/discovery/sessions/${discoverySession.session_id}`, adminToken);
        if (!response.ok) throw new Error("The discovery session could not be read.");
        const next = (await response.json()) as DiscoverySession;
        if (!cancelled) {
          setDiscoverySession(next);
          setDiscoveryError(null);
        }
      } catch (reason) {
        if (!cancelled) setDiscoveryError(reason instanceof Error ? reason.message : "Discovery polling failed.");
      }
    };
    const timer = window.setInterval(() => void poll(), 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [adminToken, discoverySession?.session_id, discoverySession?.status]);

  async function startDiscovery() {
    setDiscoveryStarting(true);
    setDiscoveryError(null);
    try {
      const response = await apiFetch("/api/v1/discovery/sessions", adminToken, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ linker_id: linkerId, timeout_s: timeoutSeconds }),
      });
      if (!response.ok) throw new Error("The server did not accept the discovery request.");
      setDiscoverySession((await response.json()) as DiscoverySession);
    } catch (reason) {
      setDiscoveryError(reason instanceof Error ? reason.message : "Discovery could not be started.");
    } finally {
      setDiscoveryStarting(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-slate-800/80 bg-[#0b1627] px-4 py-5 lg:flex lg:flex-col">
        <div className="flex items-center gap-3 px-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-cyan-300 text-slate-950">
            <Network size={19} strokeWidth={2.5} />
          </div>
          <div>
            <p className="text-sm font-semibold tracking-wide">OpenHDO</p>
            <p className="text-[11px] text-slate-500">server admin</p>
          </div>
        </div>

        <nav className="mt-10 space-y-1" aria-label="Server admin navigation">
          {navigation.map(({ label, icon: Icon }) => (
            <button
              key={label}
              type="button"
              onClick={() => setActive(label)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                active === label
                  ? "bg-cyan-300/10 text-cyan-200"
                  : "text-slate-400 hover:bg-slate-800/70 hover:text-slate-100"
              }`}
            >
              <Icon size={17} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="mt-auto rounded-xl border border-cyan-300/15 bg-cyan-300/5 p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-cyan-200">
            <StatusDot tone={error ? "amber" : "emerald"} />
            {error ? "Needs attention" : "Runtime connected"}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
            {health ? `${health.instance_name} · API v${health.api_version}` : "Waiting for server API"}
          </p>
        </div>
      </aside>

      <main className="lg:pl-64">
        <header className="flex items-center justify-between border-b border-slate-800/80 px-5 py-5 sm:px-8">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-cyan-300/70">{active}</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">Server administration</h1>
            <p className="mt-1 text-sm text-slate-500">Canonical state from this OpenHDO server.</p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => void loadData()} disabled={loading} aria-label="Refresh server data">
            <RefreshCw size={15} /> <span className="hidden sm:inline">{loading ? "Loading" : "Refresh"}</span>
          </Button>
        </header>

        <div className="border-b border-slate-800/80 bg-slate-950/20 px-5 py-3 sm:px-8">
          <label className="block max-w-xl text-xs text-slate-400" htmlFor="admin-bearer-token">
            Bearer token <span className="text-slate-600">(session only)</span>
            <input
              id="admin-bearer-token"
              type="password"
              autoComplete="current-password"
              value={adminToken}
              onChange={(event) => updateAdminToken(event.target.value)}
              onBlur={() => void loadData()}
              placeholder="Required when OPENHDO_API_TOKEN is enabled"
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2 text-sm text-slate-100 outline-none ring-cyan-300/50 focus:ring-2"
            />
          </label>
          <p className="mt-1 text-[11px] text-slate-600">Stored in this browser tab's sessionStorage; never logged or bundled.</p>
        </div>

        <div className="space-y-6 px-5 py-6 sm:px-8 sm:py-8">
          {error && (
            <div className="flex items-start gap-3 rounded-xl border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-100" role="alert">
              <CircleAlert className="mt-0.5 shrink-0 text-amber-300" size={17} />
              <div>
                <p className="font-medium">Admin data unavailable</p>
                <p className="mt-1 text-xs text-amber-100/70">{error} Configure the server bearer token if authorization is enabled.</p>
              </div>
            </div>
          )}

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Server summary">
            <SummaryCard icon={Boxes} label="Lights" value={loading ? "—" : String(lights.length)} caption="canonical registry" />
            <SummaryCard icon={Cable} label="Linkers" value={health ? String(health.linkers_connected) : "—"} caption="connected sessions" />
            <SummaryCard icon={Gauge} label="Runtime" value={health?.runtime ?? "—"} caption="active backend" />
            <SummaryCard icon={Activity} label="API" value={health ? `v${health.api_version}` : "—"} caption="versioned boundary" />
          </section>

          <section className="rounded-2xl border border-cyan-300/20 bg-[#0d192b] p-5 sm:p-6" aria-labelledby="discovery-title">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-sm font-medium"><Search size={16} className="text-cyan-300" /> <span id="discovery-title">Add device</span></div>
                <p className="mt-1 text-xs text-slate-500">Ask a connected Linker to scan for real Wi-Fi devices.</p>
              </div>
              <DiscoveryStatus session={discoverySession} />
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-[minmax(0,1fr)_9rem_auto] sm:items-end">
              <label className="block text-xs text-slate-400">
                Linker id
                <input
                  value={linkerId}
                  onChange={(event) => setLinkerId(event.target.value)}
                  pattern="^[a-z][a-z0-9._-]{1,63}$"
                  required
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2.5 text-sm text-slate-100 outline-none ring-cyan-300/50 focus:ring-2"
                />
              </label>
              <label className="block text-xs text-slate-400">
                Timeout (s)
                <input
                  type="number"
                  min={1}
                  max={60}
                  value={timeoutSeconds}
                  onChange={(event) => setTimeoutSeconds(Number(event.target.value))}
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2.5 text-sm text-slate-100 outline-none ring-cyan-300/50 focus:ring-2"
                />
              </label>
              <Button onClick={() => void startDiscovery()} disabled={discoveryStarting || discoverySession?.status === "running"}>
                <Search size={15} /> {discoveryStarting ? "Starting…" : "Scan"}
              </Button>
            </div>
            {discoveryError && <p className="mt-3 text-xs text-amber-200" role="alert">{discoveryError}</p>}
            {discoverySession && <DiscoveryResults session={discoverySession} />}
          </section>

          <section className="rounded-2xl border border-slate-800 bg-[#0d192b] p-5 sm:p-6" aria-labelledby="lights-title">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 text-sm font-medium"><Boxes size={16} className="text-cyan-300" /> <span id="lights-title">Registered Lights</span></div>
                <p className="mt-1 text-xs text-slate-500">Vendor-neutral state and capability reported by Linkers</p>
              </div>
              <ChevronRight size={16} className="text-slate-600" />
            </div>
            <div className="mt-5 space-y-3">
              {!loading && lights.length === 0 && <p className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">No lights registered. Connect a Linker and send a `link.register` message.</p>}
              {lights.map((light) => <LightRow key={light.light_id} light={light} />)}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-800 bg-[#0d192b] p-5 sm:p-6">
            <div className="flex items-center gap-2 text-sm font-medium"><Server size={16} className="text-cyan-300" /> Server-owned admin surface</div>
            <p className="mt-2 text-xs leading-relaxed text-slate-500">This panel reads the server API. Reusable client dashboards remain separate consumers of the public contracts.</p>
          </section>
        </div>
      </main>
    </div>
  );
}

function StatusDot({ tone }: { tone: "emerald" | "amber" }) {
  return <span className={`h-2 w-2 rounded-full ${tone === "emerald" ? "bg-emerald-400" : "bg-amber-400"}`} aria-hidden="true" />;
}

function SummaryCard({ icon: Icon, label, value, caption }: { icon: typeof Boxes; label: string; value: string; caption: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-[#0d192b] p-5">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">{label}</p>
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-cyan-300/10 text-cyan-200"><Icon size={16} /></div>
      </div>
      <p className="mt-5 text-3xl font-semibold tracking-tight">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{caption}</p>
    </div>
  );
}

function LightRow({ light }: { light: Light }) {
  const state = light.state;
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-800/80 bg-slate-950/20 p-3">
      <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${state?.power ? "bg-emerald-400/10 text-emerald-300" : "bg-slate-800 text-slate-500"}`}><Activity size={16} /></div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-200">{light.name}</p>
        <p className="truncate text-xs text-slate-500">{light.light_id} · Linker {light.linker_id}</p>
      </div>
      <div className="shrink-0 text-right text-xs text-slate-500">
        <p>{state ? `${state.power ? "On" : "Off"} · ${state.brightness}/255` : "State pending"}</p>
        <p className="mt-1">{light.capability.color_modes?.join("/") ?? "Light"}</p>
      </div>
    </div>
  );
}

function DiscoveryStatus({ session }: { session: DiscoverySession | null }) {
  if (!session) return <span className="text-xs text-slate-500">Ready to scan</span>;
  const tone = session.status === "failed" ? "text-amber-200" : session.status === "completed" ? "text-emerald-300" : "text-cyan-200";
  return <span className={`text-xs ${tone}`}>{session.status === "running" ? "Scanning…" : session.status}</span>;
}

function DiscoveryResults({ session }: { session: DiscoverySession }) {
  return (
    <div className="mt-5 border-t border-slate-800 pt-4">
      <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
        <span className="flex items-center gap-2"><Clock3 size={14} /> Session {session.session_id}</span>
        <span>{session.candidates.length} candidate{session.candidates.length === 1 ? "" : "s"}</span>
      </div>
      {session.error && <p className="mt-3 text-sm text-amber-200">{session.error}</p>}
      {session.candidates.length === 0 ? (
        <p className="mt-3 rounded-xl border border-dashed border-slate-700 p-4 text-sm text-slate-500">
          {session.status === "running" ? "No candidates reported yet." : "No devices found by the connected Linker."}
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {session.candidates.map((candidate) => (
            <div key={candidate.candidate_id} className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800/80 bg-slate-950/20 p-3">
              <CircleCheck size={16} className="text-emerald-300" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-slate-200">{candidate.name}</p>
                <p className="truncate text-xs text-slate-500">{candidate.candidate_id} · {candidate.transport}</p>
              </div>
              <div className="text-right text-xs text-slate-500">
                <p>{candidate.capabilities.length} light capabilit{candidate.capabilities.length === 1 ? "y" : "ies"}</p>
                <p className={candidate.requires_pairing ? "mt-1 text-amber-200" : "mt-1 text-emerald-300"}>
                  {candidate.requires_pairing ? "Pairing required" : "No pairing required"}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
