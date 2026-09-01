import { useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Boxes,
  Cable,
  Check,
  ChevronRight,
  CircleAlert,
  Cpu,
  Gauge,
  LayoutDashboard,
  LifeBuoy,
  Network,
  Radio,
  RefreshCw,
  Server,
  Settings,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { Button } from "./components/ui/button";

const navigation = [
  { label: "Overview", icon: LayoutDashboard },
  { label: "Devices", icon: Boxes },
  { label: "Flows", icon: Workflow },
  { label: "Linkers", icon: Cable },
];

const activity = [
  { title: "Kitchen light turned on", detail: "Flow · Evening scene", time: "2 min ago", color: "bg-emerald-400" },
  { title: "Linker reconnected", detail: "Hallway gateway · Zigbee", time: "14 min ago", color: "bg-cyan-400" },
  { title: "Temperature threshold reached", detail: "Living room · 24.8°C", time: "31 min ago", color: "bg-amber-400" },
  { title: "Firmware check completed", detail: "4 devices checked", time: "1 hr ago", color: "bg-violet-400" },
];

function StatusDot({ tone = "emerald" }: { tone?: "emerald" | "amber" | "red" }) {
  const colors = { emerald: "bg-emerald-400", amber: "bg-amber-400", red: "bg-red-400" };
  return <span className={`h-2 w-2 rounded-full ${colors[tone]}`} aria-hidden="true" />;
}

export default function App() {
  const [active, setActive] = useState("Overview");

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-slate-800/80 bg-[#0b1627] px-4 py-5 lg:flex lg:flex-col">
        <div className="flex items-center gap-3 px-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-cyan-300 text-slate-950">
            <Network size={19} strokeWidth={2.5} />
          </div>
          <div>
            <p className="text-sm font-semibold tracking-wide">OpenHDO</p>
            <p className="text-[11px] text-slate-500">control plane</p>
          </div>
        </div>

        <nav className="mt-10 space-y-1" aria-label="Main navigation">
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
              {label === "Linkers" && <span className="ml-auto text-[10px] text-slate-600">3</span>}
            </button>
          ))}
        </nav>

        <div className="mt-auto space-y-1">
          <button type="button" className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-400 hover:bg-slate-800/70 hover:text-slate-100">
            <Settings size={17} /> Settings
          </button>
          <div className="mt-5 rounded-xl border border-emerald-400/15 bg-emerald-400/5 p-3">
            <div className="flex items-center gap-2 text-xs font-medium text-emerald-300"><StatusDot /> Runtime healthy</div>
            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">openhdo-server 0.1.0 · protocol v1</p>
          </div>
        </div>
      </aside>

      <main className="lg:pl-64">
        <header className="flex items-center justify-between border-b border-slate-800/80 px-5 py-5 sm:px-8">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-cyan-300/70">{active}</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">Good evening, Alex</h1>
            <p className="mt-1 text-sm text-slate-500">Your home is quiet and running smoothly.</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden rounded-full border border-amber-300/20 bg-amber-300/10 px-2.5 py-1 text-[11px] font-medium text-amber-200 sm:inline">Foundation preview</span>
            <Button variant="secondary" size="sm" aria-label="Refresh overview">
              <RefreshCw size={15} /> <span className="hidden sm:inline">Refresh</span>
            </Button>
          </div>
        </header>

        <nav className="flex gap-2 overflow-x-auto border-b border-slate-800/80 px-5 py-3 lg:hidden" aria-label="Mobile navigation">
          {navigation.map(({ label, icon: Icon }) => (
            <button
              key={label}
              type="button"
              onClick={() => setActive(label)}
              className={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium ${
                active === label ? "bg-cyan-300/10 text-cyan-200" : "text-slate-500 hover:bg-slate-800/70 hover:text-slate-200"
              }`}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
        </nav>

        <div className="space-y-6 px-5 py-6 sm:px-8 sm:py-8">
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="System summary">
            <SummaryCard icon={Boxes} label="Devices" value="24" caption="22 online" tone="cyan" />
            <SummaryCard icon={Workflow} label="Active flows" value="8" caption="All healthy" tone="violet" />
            <SummaryCard icon={Gauge} label="Avg. temperature" value="22.4°" caption="Within comfort range" tone="amber" />
            <SummaryCard icon={ShieldCheck} label="Security" value="100%" caption="No open alerts" tone="emerald" />
          </section>

          <section className="grid gap-6 xl:grid-cols-[1.35fr_1fr]">
            <div className="rounded-2xl border border-slate-800 bg-[#0d192b] p-5 sm:p-6">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm font-medium"><Activity size={16} className="text-cyan-300" /> Activity</div>
                  <p className="mt-1 text-xs text-slate-500">Latest events across your environment</p>
                </div>
                <Button variant="ghost" size="sm">View all <ArrowUpRight size={14} /></Button>
              </div>
              <div className="mt-5 divide-y divide-slate-800/80">
                {activity.map((item) => (
                  <div key={item.title} className="flex items-center gap-3 py-3.5 first:pt-0 last:pb-0">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${item.color}`} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-slate-200">{item.title}</p>
                      <p className="mt-0.5 truncate text-xs text-slate-500">{item.detail}</p>
                    </div>
                    <span className="shrink-0 text-[11px] text-slate-600">{item.time}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-[#0d192b] p-5 sm:p-6">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm font-medium"><Cable size={16} className="text-cyan-300" /> Connected Linkers</div>
                  <p className="mt-1 text-xs text-slate-500">Hardware access points</p>
                </div>
                <Button variant="ghost" size="sm">Manage <ChevronRight size={14} /></Button>
              </div>
              <div className="mt-5 space-y-3">
                <LinkerRow name="Hallway gateway" host="raspberrypi.local" devices="12 devices" status="Online" />
                <LinkerRow name="Office bridge" host="office-mini.local" devices="8 devices" status="Online" />
                <LinkerRow name="Garage sensor hub" host="garage-pi.local" devices="4 devices" status="Degraded" tone="amber" />
              </div>
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-3">
            <QuickAction icon={Radio} title="Discover devices" copy="Scan connected transports" />
            <QuickAction icon={Workflow} title="Create a flow" copy="Automate an everyday action" />
            <QuickAction icon={LifeBuoy} title="Run diagnostics" copy="Check runtime and linkers" />
          </section>
        </div>
      </main>
    </div>
  );
}

function SummaryCard({ icon: Icon, label, value, caption, tone }: { icon: typeof Boxes; label: string; value: string; caption: string; tone: "cyan" | "violet" | "amber" | "emerald" }) {
  const styles = {
    cyan: "bg-cyan-300/10 text-cyan-200",
    violet: "bg-violet-300/10 text-violet-200",
    amber: "bg-amber-300/10 text-amber-200",
    emerald: "bg-emerald-300/10 text-emerald-200",
  };
  return (
    <div className="rounded-2xl border border-slate-800 bg-[#0d192b] p-5">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">{label}</p>
        <div className={`grid h-8 w-8 place-items-center rounded-lg ${styles[tone]}`}><Icon size={16} /></div>
      </div>
      <p className="mt-5 text-3xl font-semibold tracking-tight">{value}</p>
      <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-500"><Check size={13} className="text-emerald-400" /> {caption}</p>
    </div>
  );
}

function LinkerRow({ name, host, devices, status, tone = "emerald" }: { name: string; host: string; devices: string; status: string; tone?: "emerald" | "amber" }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-800/80 bg-slate-950/20 p-3">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-800 text-slate-400"><Server size={16} /></div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-200">{name}</p>
        <p className="truncate text-xs text-slate-500">{host} · {devices}</p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5 text-[11px] text-slate-500"><StatusDot tone={tone} /> {status}</div>
    </div>
  );
}

function QuickAction({ icon: Icon, title, copy }: { icon: typeof Radio; title: string; copy: string }) {
  return (
    <button type="button" className="group flex items-center gap-4 rounded-2xl border border-slate-800 bg-[#0d192b] p-4 text-left transition-colors hover:border-cyan-300/30 hover:bg-[#102139]">
      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-cyan-300/10 text-cyan-200"><Icon size={18} /></div>
      <div className="min-w-0 flex-1"><p className="text-sm font-medium text-slate-200">{title}</p><p className="mt-1 text-xs text-slate-500">{copy}</p></div>
      <ChevronRight size={16} className="text-slate-600 transition-transform group-hover:translate-x-0.5 group-hover:text-cyan-300" />
    </button>
  );
}
