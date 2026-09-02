import { SignOut } from "@phosphor-icons/react/SignOut";
import { useEffect, useState, useSyncExternalStore } from "react";

import { getPanelModules, subscribeToModules } from "./modules/load";
import type { PanelAuthUser, PanelModule, PanelModuleContext } from "./modules/registry";

type AuthState =
  | { status: "loading"; user: null }
  | { status: "login"; user: null }
  | { status: "authenticated"; user: PanelAuthUser };

type ApiError = { detail?: string };

const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

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

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ status: "loading", user: null });
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginPending, setLoginPending] = useState(false);

  useEffect(() => {
    let mounted = true;
    requestFromModule("/api/v1/auth/me")
      .then(async (response) => {
        if (!mounted) return;
        if (!response.ok) {
          setAuth({ status: "login", user: null });
          return;
        }
        const payload = (await response.json()) as { user: PanelAuthUser };
        setAuth({ status: "authenticated", user: payload.user });
      })
      .catch(() => {
        if (mounted) {
          setLoginError("Server unavailable");
          setAuth({ status: "login", user: null });
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

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
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : "Unable to sign in");
    } finally {
      setLoginPending(false);
    }
  }

  async function logout() {
    const response = await requestFromModule("/api/v1/auth/logout", { method: "POST" });
    if (!response.ok && response.status !== 401) throw new Error(await responseError(response));
    setAuth({ status: "login", user: null });
  }

  if (auth.status === "loading") return <LoadingScreen />;
  if (auth.status === "login") {
    return <LoginScreen onSubmit={login} pending={loginPending} error={loginError} />;
  }
  return <AuthenticatedPanel user={auth.user} onLogout={logout} />;
}

function LoadingScreen() {
  return (
    <div className="grid min-h-screen place-items-center bg-[#0a0a0a]">
      <img src="/admin/brand/OpenHDO-green.png" alt="OpenHDO" className="h-10 w-10 animate-pulse" />
    </div>
  );
}

function LoginScreen({ onSubmit, pending, error }: { onSubmit: (username: string, password: string) => Promise<void>; pending: boolean; error: string | null }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  return (
    <main className="grid min-h-screen place-items-center bg-[#0a0a0a] px-5 text-slate-100">
      <form
        className="w-full max-w-sm space-y-6"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit(username, password);
        }}
      >
        <div className="flex items-center gap-3">
          <img src="/admin/brand/OpenHDO-green.png" alt="OpenHDO" className="h-9 w-9" />
          <span className="font-brand text-xl font-bold tracking-tight">Admin</span>
        </div>
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
              autoComplete="current-password"
              required
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="h-11 rounded-md border border-neutral-700 bg-neutral-950 px-3 text-neutral-100 outline-none transition focus:border-accent"
            />
          </label>
        </div>
        {error && <p className="border-y border-red-900/70 py-3 text-sm text-red-300">{error}</p>}
        <button
          type="submit"
          disabled={pending}
          className="h-11 w-full rounded-md bg-accent px-4 text-sm font-semibold text-neutral-950 transition hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

function AuthenticatedPanel({ user, onLogout }: { user: PanelAuthUser; onLogout: () => Promise<void> }) {
  const panelItems = useSyncExternalStore(subscribeToModules, getPanelModules, getPanelModules);
  const visibleItems = panelItems.filter((item) => !item.requiredRoles || item.requiredRoles.includes(user.role));
  const [activeId, setActiveId] = useState<string | null>(visibleItems[0]?.id ?? null);
  const [logoutPending, setLogoutPending] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const activeItem = visibleItems.find((item) => item.id === activeId) ?? visibleItems[0];
  const moduleContext: PanelModuleContext = {
    navigate: setActiveId,
    api: { request: requestFromModule },
    auth: { user, logout: onLogout },
  };

  async function handleLogout() {
    setLogoutPending(true);
    setLogoutError(null);
    try {
      await onLogout();
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : "Unable to sign out");
    } finally {
      setLogoutPending(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-100">
      <header className="flex h-16 items-center justify-between border-b border-neutral-800 px-4 min-[390px]:px-5 md:px-6 wide:px-8">
        <div className="flex items-center gap-3">
          <img src="/admin/brand/OpenHDO-green.png" alt="OpenHDO" className="h-8 w-8" />
          <span className="font-brand text-lg font-bold tracking-tight">Admin</span>
        </div>
        <button
          type="button"
          aria-label="Sign out"
          title="Sign out"
          disabled={logoutPending}
          onClick={() => void handleLogout()}
          className="rounded-md p-2 text-neutral-400 transition hover:bg-neutral-900 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60"
        >
          <SignOut size={19} aria-hidden="true" />
        </button>
      </header>

      {logoutError && <div className="border-b border-red-900/70 px-4 py-3 text-sm text-red-300 min-[390px]:px-5 md:px-6">{logoutError}</div>}

      <div className="flex flex-col md:grid md:min-h-[calc(100vh-4rem)] md:grid-cols-[13rem_1fr] wide:grid-cols-[15rem_1fr]">
        <aside className="border-b border-neutral-800 px-4 py-3 min-[390px]:px-5 md:border-b-0 md:border-r md:px-3 md:py-5 wide:px-4" aria-label="Panel navigation">
          <nav className="flex gap-1 overflow-x-auto md:h-full md:flex-col" aria-label="Modules">
            {visibleItems.map((item) => <ModuleLink key={item.id} item={item} activeId={activeId} onSelect={setActiveId} />)}
          </nav>
        </aside>

        <main className="min-w-0 px-4 py-6 min-[390px]:px-5 md:px-8 md:py-8 wide:px-12" aria-label={activeItem ? `${activeItem.label} module` : "Panel modules"}>
          {activeItem ? <activeItem.component context={moduleContext} /> : <p className="text-sm text-neutral-500">No modules</p>}
        </main>
      </div>
    </div>
  );
}

function ModuleLink({ item, activeId, onSelect }: { item: PanelModule; activeId: string | null; onSelect: (id: string) => void }) {
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
