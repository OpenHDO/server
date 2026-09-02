import Avatar from "boring-avatars";
import { CaretDown } from "@phosphor-icons/react/CaretDown";
import { GearSix } from "@phosphor-icons/react/GearSix";
import { House } from "@phosphor-icons/react/House";
import { SignIn } from "@phosphor-icons/react/SignIn";
import { SignOut } from "@phosphor-icons/react/SignOut";
import { SquaresFour } from "@phosphor-icons/react/SquaresFour";
import { UserPlus } from "@phosphor-icons/react/UserPlus";
import { UsersThree } from "@phosphor-icons/react/UsersThree";
import { useEffect, useState, useSyncExternalStore } from "react";

import { getPanelModules, subscribeToModules } from "./modules/load";
import type { PanelAuthUser, PanelModule, PanelModuleContext } from "./modules/registry";
import SettingsView from "./builtins/settings";
import UsersView from "./builtins/users";

type AuthMode = "login" | "register";
type PageRoute = "home" | "admin" | "auth" | "not-found";
type AuthState =
  | { status: "loading"; user: null }
  | { status: "guest"; user: null }
  | { status: "authenticated"; user: PanelAuthUser };
type ApiError = { detail?: string };
type PanelNavigationItem = {
  id: string;
  label: string;
  icon: PanelModule["icon"];
  component: PanelModule["component"];
  requiredRoles?: PanelModule["requiredRoles"];
  order?: number;
};

const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const pageRoute = resolveRoute(window.location.pathname);
const builtInItems: PanelNavigationItem[] = [
  { id: "users", label: "Users", icon: UsersThree, component: UsersView, requiredRoles: ["admin"], order: 40 },
  { id: "settings", label: "Settings", icon: GearSix, component: SettingsView, requiredRoles: ["admin"], order: 50 },
];

function resolveRoute(pathname: string): PageRoute {
  if (pathname === "/") return "home";
  if (pathname === "/admin" || pathname === "/admin/") return "admin";
  if (pathname === "/auth" || pathname === "/auth/") return "auth";
  return "not-found";
}

function cookieValue(name: string) {
  const prefix = `${name}=`;
  const cookie = document.cookie.split("; ").find((value) => value.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

function requestFromModule(input: RequestInfo | URL, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  const method = (init?.method ?? "GET").toUpperCase();
  const csrf = cookieValue("openhdo_csrf");
  if (unsafeMethods.has(method) && csrf) headers.set("X-OpenHDO-CSRF", csrf);
  return fetch(input, { ...init, headers, credentials: init?.credentials ?? "same-origin" });
}

async function responseError(response: Response) {
  const payload = (await response.json().catch(() => null)) as ApiError | null;
  return payload?.detail ?? `Request failed (${response.status})`;
}

function nextPath() {
  const requested = new URLSearchParams(window.location.search).get("next");
  return requested && requested.startsWith("/") && !requested.startsWith("//") ? requested : "/admin/";
}

function openAuthPage(mode: AuthMode) {
  window.location.assign(`/auth?mode=${mode}&next=${encodeURIComponent(window.location.pathname)}`);
}

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ status: "loading", user: null });
  const [authError, setAuthError] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginPending, setLoginPending] = useState(false);

  useEffect(() => {
    if (pageRoute === "not-found") return;
    let mounted = true;
    requestFromModule("/api/v1/auth/me")
      .then(async (response) => {
        if (!mounted) return;
        if (!response.ok) {
          setAuth({ status: "guest", user: null });
          return;
        }
        const payload = (await response.json()) as { user: PanelAuthUser };
        setAuthError(null);
        setAuth({ status: "authenticated", user: payload.user });
      })
      .catch(() => {
        if (mounted) {
          setAuthError("Server unavailable");
          setLoginError("Server unavailable");
          setAuth({ status: "guest", user: null });
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (pageRoute === "auth" && auth.status === "authenticated") window.location.replace(nextPath());
  }, [auth.status]);

  useEffect(() => {
    if (pageRoute === "admin" && auth.status === "guest") window.location.replace("/");
  }, [auth.status]);

  async function login(username: string, password: string) {
    setLoginPending(true);
    setLoginError(null);
    try {
      const response = await requestFromModule("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const payload = (await response.json()) as { user: PanelAuthUser };
      setAuth({ status: "authenticated", user: payload.user });
      return true;
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : "Unable to sign in");
      return false;
    } finally {
      setLoginPending(false);
    }
  }

  async function logout() {
    const response = await requestFromModule("/api/v1/auth/logout", { method: "POST" });
    if (!response.ok && response.status !== 401) throw new Error(await responseError(response));
    setAuth({ status: "guest", user: null });
  }

  if (pageRoute === "not-found") return <NotFoundPage />;
  if (auth.status === "loading") return <LoadingScreen />;
  if (pageRoute === "home") {
    return <HomePage user={auth.status === "authenticated" ? auth.user : null} authError={authError} onLogout={logout} />;
  }
  if (pageRoute === "auth") {
    if (auth.status === "authenticated") return <LoadingScreen />;
    return (
      <AuthPage
        initialMode={new URLSearchParams(window.location.search).get("mode") === "register" ? "register" : "login"}
        onLogin={login}
        loginPending={loginPending}
        loginError={loginError}
      />
    );
  }
  if (auth.status === "guest") {
    return <LoadingScreen />;
  }
  return <PanelShell user={auth.status === "authenticated" ? auth.user : null} onLogin={() => openAuthPage("login")} onLogout={logout} />;
}

function LoadingScreen() {
  return (
    <div className="grid min-h-screen place-items-center bg-[#0a0a0a]">
      <img src="/admin/brand/OpenHDO-green.png" alt="OpenHDO" className="h-10 w-10 animate-pulse" />
    </div>
  );
}

function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-[#0a0a0a] px-5 text-slate-100">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div className="flex items-center justify-center gap-3">
          <img src="/admin/brand/OpenHDO-green.png" alt="OpenHDO" className="h-9 w-9" />
          <span className="font-brand text-xl font-bold tracking-tight">OpenHDO</span>
        </div>
        <div className="space-y-2">
          <p className="font-brand text-6xl font-bold tracking-tight text-accent">404</p>
          <h1 className="font-brand text-2xl font-bold tracking-tight">Page not found</h1>
        </div>
        <a
          href="/"
          className="inline-flex items-center gap-2 rounded-md border border-neutral-700 px-4 py-2 text-sm text-neutral-200 transition hover:border-neutral-500 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <House size={18} aria-hidden="true" />
          Go home
        </a>
      </div>
    </main>
  );
}

function HomePage({ user, authError, onLogout }: { user: PanelAuthUser | null; authError: string | null; onLogout: () => Promise<void> }) {
  return (
    <main className="min-h-screen bg-[#0a0a0a] text-slate-100">
      <div className="fixed left-4 top-4 z-20 min-[390px]:left-5 min-[390px]:top-5">
        <MiniProfile user={user} authNext="/" authError={authError} onLogout={onLogout} />
      </div>
    </main>
  );
}

function AuthPage({
  initialMode,
  onLogin,
  loginPending,
  loginError,
}: {
  initialMode: AuthMode;
  onLogin: (username: string, password: string) => Promise<boolean>;
  loginPending: boolean;
  loginError: string | null;
}) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [registerPending, setRegisterPending] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const busy = loginPending || registerPending;

  function changeMode(next: AuthMode) {
    setMode(next);
    setPassword("");
    setRegisterError(null);
    window.history.replaceState({}, "", `/auth?mode=${next}&next=${encodeURIComponent(nextPath())}`);
  }

  async function register() {
    setRegisterPending(true);
    setRegisterError(null);
    try {
      const response = await requestFromModule("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      if (!(await onLogin(username, password))) throw new Error("Unable to sign in");
    } catch (error) {
      setRegisterError(error instanceof Error ? error.message : "Unable to create account");
    } finally {
      setRegisterPending(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#0a0a0a] px-5 text-slate-100">
      <form
        className="w-full max-w-sm space-y-6"
        onSubmit={(event) => {
          event.preventDefault();
          if (mode === "login") void onLogin(username, password);
          else void register();
        }}
      >
        <div className="flex items-center gap-3">
          <img src="/admin/brand/OpenHDO-green.png" alt="OpenHDO" className="h-9 w-9" />
          <span className="font-brand text-xl font-bold tracking-tight">OpenHDO</span>
        </div>
        <div className="flex gap-5 border-b border-neutral-800 text-sm">
          <button type="button" onClick={() => changeMode("login")} className={`border-b-2 pb-3 ${mode === "login" ? "border-accent text-neutral-100" : "border-transparent text-neutral-500"}`}>Sign in</button>
          <button type="button" onClick={() => changeMode("register")} className={`border-b-2 pb-3 ${mode === "register" ? "border-accent text-neutral-100" : "border-transparent text-neutral-500"}`}>Register</button>
        </div>
        <h1 className="font-brand text-2xl font-bold tracking-tight">{mode === "login" ? "Sign in" : "Create account"}</h1>
        <div className="space-y-3">
          <label className="grid gap-2 text-sm text-neutral-300">
            Username
            <input
              autoComplete="username"
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="h-11 rounded-md border border-neutral-700 bg-neutral-950 px-3 text-neutral-100 outline-none transition focus:border-accent"
            />
          </label>
          <label className="grid gap-2 text-sm text-neutral-300">
            Password
            <input
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
              minLength={8}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="h-11 rounded-md border border-neutral-700 bg-neutral-950 px-3 text-neutral-100 outline-none transition focus:border-accent"
            />
          </label>
        </div>
        {(mode === "login" ? loginError : registerError) && <p className="border-y border-red-900/70 py-3 text-sm text-red-300">{mode === "login" ? loginError : registerError}</p>}
        <button
          type="submit"
          disabled={busy}
          className="h-11 w-full rounded-md bg-accent px-4 text-sm font-semibold text-neutral-950 transition hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60"
        >
          {busy ? (mode === "login" ? "Signing in…" : "Creating…") : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>
    </main>
  );
}

function PanelShell({ user, onLogin, onLogout }: { user: PanelAuthUser | null; onLogin: () => void; onLogout: () => Promise<void> }) {
  const panelItems = useSyncExternalStore(subscribeToModules, getPanelModules, getPanelModules);
  const navigationItems = [...panelItems, ...builtInItems].sort((left, right) => (left.order ?? Number.MAX_SAFE_INTEGER) - (right.order ?? Number.MAX_SAFE_INTEGER));
  const [activeId, setActiveId] = useState<string | null>(navigationItems[0]?.id ?? null);
  const activeItem = navigationItems.find((item) => item.id === activeId) ?? navigationItems[0];
  const selectItem = (id: string) => {
    const item = navigationItems.find((candidate) => candidate.id === id);
    if (!item) return;
    if (item.requiredRoles && (!user || !item.requiredRoles.includes(user.role))) {
      window.location.assign("/");
      return;
    }
    setActiveId(id);
  };
  const moduleContext: PanelModuleContext = {
    navigate: selectItem,
    api: { request: requestFromModule },
    auth: { user, login: onLogin, logout: onLogout },
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-100">
      <header className="flex h-16 items-center justify-between border-b border-neutral-800 px-4 min-[390px]:px-5 md:px-6 wide:px-8">
        <div className="flex items-center gap-3">
          <a href="/" aria-label="OpenHDO home" className="rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
            <img src="/admin/brand/OpenHDO-green.png" alt="OpenHDO" className="h-8 w-8" />
          </a>
          <span className="font-brand text-lg font-bold tracking-tight">Admin</span>
        </div>
        <MiniProfile user={user} onLogout={onLogout} />
      </header>

      <div className="flex flex-col md:grid md:min-h-[calc(100vh-4rem)] md:grid-cols-[13rem_1fr] wide:grid-cols-[15rem_1fr]">
        <aside className="border-b border-neutral-800 px-4 py-3 min-[390px]:px-5 md:border-b-0 md:border-r md:px-3 md:py-5 wide:px-4" aria-label="Panel navigation">
          <nav className="flex gap-1 overflow-x-auto md:h-full md:flex-col" aria-label="Modules">
            {navigationItems.map((item) => <ModuleLink key={item.id} item={item} activeId={activeId} onSelect={selectItem} />)}
          </nav>
        </aside>

        <main className="min-w-0 px-4 py-6 min-[390px]:px-5 md:px-8 md:py-8 wide:px-12" aria-label={activeItem ? `${activeItem.label} module` : "Panel modules"}>
          {activeItem ? <activeItem.component context={moduleContext} /> : null}
        </main>
      </div>
    </div>
  );
}

function MiniProfile({ user, authNext = "/admin/", authError, onLogout }: { user: PanelAuthUser | null; authNext?: string; authError?: string | null; onLogout: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const menuPosition = authNext === "/" ? "left-0" : "right-0";

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  async function handleLogout() {
    setPending(true);
    setError(null);
    try {
      await onLogout();
      setOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to sign out");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={user ? `Open profile for ${user.username}` : "Open sign in menu"}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((current) => !current)}
        className="flex items-center gap-2 rounded-full bg-neutral-950/80 p-1 text-neutral-300 shadow-lg transition hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        {user ? <Avatar name={user.username} size={36} variant="beam" colors={avatarColors} title={false} className="rounded-full" /> : <span className="grid h-9 w-9 place-items-center rounded-full bg-neutral-800 text-neutral-400"><SignIn size={18} aria-hidden="true" /></span>}
        <CaretDown size={14} className={`hidden text-neutral-500 transition-transform min-[390px]:block ${open ? "rotate-180" : ""}`} aria-hidden="true" />
      </button>

      {open && <div role="menu" className={`absolute ${menuPosition} top-12 z-20 min-w-44 rounded-md border border-neutral-800 bg-neutral-950 p-1 shadow-2xl`}>
        {user ? <>
          <div className="border-b border-neutral-800 px-3 py-2">
            <div className="text-sm text-neutral-100">{user.username}</div>
            <div className="mt-1 text-xs text-neutral-500">{user.role}</div>
          </div>
          {user.role === "admin" && <a role="menuitem" href="/admin/" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded px-3 py-2 text-sm text-neutral-300 transition hover:bg-neutral-900 hover:text-neutral-100"><SquaresFour size={17} aria-hidden="true" />Admin panel</a>}
          <button type="button" role="menuitem" disabled={pending} onClick={() => void handleLogout()} className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-neutral-300 transition hover:bg-neutral-900 hover:text-neutral-100 disabled:opacity-60"><SignOut size={17} aria-hidden="true" />Sign out</button>
        </> : <>
          <a role="menuitem" href={`/auth?mode=login&next=${encodeURIComponent(authNext)}`} onClick={() => setOpen(false)} className="flex items-center gap-2 rounded px-3 py-2 text-sm text-neutral-300 transition hover:bg-neutral-900 hover:text-neutral-100"><SignIn size={17} aria-hidden="true" />Sign in</a>
          <a role="menuitem" href={`/auth?mode=register&next=${encodeURIComponent(authNext)}`} onClick={() => setOpen(false)} className="flex items-center gap-2 rounded px-3 py-2 text-sm text-neutral-300 transition hover:bg-neutral-900 hover:text-neutral-100"><UserPlus size={17} aria-hidden="true" />Register</a>
        </>}
        {authError && <div className="border-t border-red-900/70 px-3 py-2 text-xs text-red-300">{authError}</div>}
        {error && <div className="border-t border-red-900/70 px-3 py-2 text-xs text-red-300">{error}</div>}
      </div>}
    </div>
  );
}

const avatarColors = ["#e879f9", "#38bdf8", "#fcd34d", "#a3e635", "#a78bfa"];

function ModuleLink({ item, activeId, onSelect }: { item: PanelNavigationItem; activeId: string | null; onSelect: (id: string) => void }) {
  const active = item.id === activeId;
  const Icon = item.icon;
  return (
    <button
      type="button"
      aria-current={active ? "page" : undefined}
      onClick={() => onSelect(item.id)}
      className={`flex shrink-0 items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-50 ${
        active ? "bg-accent/10 text-accent-muted" : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-100"
      }`}
    >
      <Icon size={18} weight={active ? "fill" : "regular"} aria-hidden="true" />
      {item.label}
    </button>
  );
}
