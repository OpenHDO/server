import { useEffect, useState } from "react";
import {
  Activity,
  Boxes,
  Cable,
  ChevronRight,
  CircleAlert,
  Gauge,
  LayoutDashboard,
  Network,
  RefreshCw,
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

const navigation = [
  { label: "Overview", icon: LayoutDashboard },
  { label: "Lights", icon: Boxes },
  { label: "Linkers", icon: Cable },
  { label: "Settings", icon: Settings },
];

export default function App() {
  const [active, setActive] = useState("Overview");
  const [health, setHealth] = useState<Health | null>(null);
  const [lights, setLights] = useState<Light[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [healthResponse, lightsResponse] = await Promise.all([
        fetch("/api/v1/health"),
        fetch("/api/v1/lights"),
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
