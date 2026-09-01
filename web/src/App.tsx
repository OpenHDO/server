import { useState } from "react";
import { getPanelModules, type PanelItem } from "./modules/registry";

const panelItems = getPanelModules();

export default function App() {
  const [activeId, setActiveId] = useState(panelItems[0].id);
  const activeItem = panelItems.find((item) => item.id === activeId) ?? panelItems[0];
  const ActiveModule = activeItem.component;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-100">
      <header className="flex h-16 items-center border-b border-neutral-800 px-4 min-[390px]:px-5 md:px-6 wide:px-8">
        <div className="flex items-center gap-3">
          <img src="/admin/brand/OpenHDO-green.png" alt="OpenHDO" className="h-8 w-8" />
          <span className="font-brand text-lg font-bold tracking-tight">Admin</span>
        </div>
      </header>

      <div className="flex flex-col md:grid md:min-h-[calc(100vh-4rem)] md:grid-cols-[13rem_1fr] wide:grid-cols-[15rem_1fr]">
        <aside className="border-b border-neutral-800 px-4 py-3 min-[390px]:px-5 md:border-b-0 md:border-r md:px-3 md:py-5 wide:px-4" aria-label="Panel navigation">
          <div className="flex gap-1 overflow-x-auto md:h-full md:flex-col">
            <nav className="flex shrink-0 gap-1 md:flex-col" aria-label="Modules">
              {panelItems.map((item) => (
                <ModuleLink key={item.id} item={item} activeId={activeId} onSelect={setActiveId} />
              ))}
            </nav>
          </div>
        </aside>

        <main className="min-w-0 px-4 py-6 min-[390px]:px-5 md:px-8 md:py-8 wide:px-12" aria-label={`${activeItem.label} module`}>
          <ActiveModule />
        </main>
      </div>
    </div>
  );
}

function ModuleLink({ item, activeId, onSelect }: { item: PanelItem; activeId: string; onSelect: (id: string) => void }) {
  const active = item.id === activeId;
  return (
    <button
      type="button"
      aria-current={active ? "page" : undefined}
      onClick={() => onSelect(item.id)}
      className={`flex shrink-0 items-center rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-50 ${
        active ? "bg-accent/10 text-accent-muted" : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-100"
      }`}
    >
      {item.label}
    </button>
  );
}
