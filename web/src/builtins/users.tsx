import { useTranslation } from "react-i18next";
import { t, responseError, formatDate } from "../i18n";
import { useNotifications } from "../notifications";
import { useEffect, useState } from "react";

import { CircleNotch } from "@phosphor-icons/react/CircleNotch";
import { Trash } from "@phosphor-icons/react/Trash";
import { WarningCircle } from "@phosphor-icons/react/WarningCircle";
import type { PanelAuthUser, PanelModuleContext, PanelUserRole } from "../modules/registry";

const roles: PanelUserRole[] = ["user", "admin"];
const registrationDate = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

type RequestError = { detail?: string };



export default function UsersView({ context }: { context: PanelModuleContext }) {
  const { t } = useTranslation();
  const notify = useNotifications();
  const [users, setUsers] = useState<PanelAuthUser[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  useEffect(() => { if (actionError) notify("error", actionError); }, [actionError, notify]);
  useEffect(() => { if (success) notify("success", success); }, [success, notify]);
  useEffect(() => { if (loadError) notify("error", loadError, { label: "Retry", onClick: () => void loadUsers() }); }, [loadError, notify]);

  async function loadUsers() {
    setLoadState("loading");
    setLoadError(null);
    try {
      const response = await context.api.request("/api/v1/admin/users");
      if (!response.ok) throw new Error(await responseError(response));
      const payload = (await response.json()) as { users: PanelAuthUser[] };
      setUsers(payload.users);
      setLoadState("ready");
    } catch (error) {
      setLoadState("error");
      setLoadError(error instanceof Error ? error.message : t("Unable to load users"));
    }
  }

  useEffect(() => {
    void loadUsers();
  }, []);

  async function updateUser(user: PanelAuthUser, change: Pick<PanelAuthUser, "role">) {
    setPendingId(user.id);
    setActionError(null);
    setSuccess(null);
    try {
      const response = await context.api.request(`/api/v1/admin/users/${user.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(change),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const updated = (await response.json()) as PanelAuthUser;
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSuccess(t("User updated"));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : t("Unable to update user"));
    } finally {
      setPendingId(null);
    }
  }

  async function deleteUser(user: PanelAuthUser) {
    if (!window.confirm(t("Delete {{name}}?", { name: user.username }))) return;
    setPendingId(user.id);
    setActionError(null);
    setSuccess(null);
    try {
      const response = await context.api.request(`/api/v1/admin/users/${user.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await responseError(response));
      setUsers((current) => current.filter((item) => item.id !== user.id));
      setSuccess(t("User deleted"));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : t("Unable to delete user"));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="w-full max-w-4xl space-y-3">
      <h1 className="font-brand text-xl font-bold tracking-tight sm:text-2xl">{t("Users")}</h1>

      {loadState === "loading" && <StatusMessage tone="loading" message={t("Loading users")} />}
      {loadState === "ready" && users.length === 0 && <StatusMessage tone="empty" message={t("No users")} />}
      {loadState === "ready" && users.length > 0 && (
        <div className="rounded-lg">
          <table aria-label={t("Users")} className="block w-full text-left text-sm lg:table">
            <thead className="sr-only border-b border-neutral-800 text-xs text-neutral-500 lg:not-sr-only">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">{t("User")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("Role")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("Registered")}</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">{t("Action")}</th>
              </tr>
            </thead>
            <tbody className="grid gap-2 lg:table-row-group lg:divide-y lg:divide-neutral-800">
              {users.map((user) => (
                <tr key={user.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 rounded-lg bg-neutral-900/50 p-3 lg:table-row lg:rounded-none lg:bg-transparent lg:p-0">
                  <td className="min-w-0 font-medium text-neutral-100 lg:px-3 lg:py-2.5">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="min-w-0 [overflow-wrap:anywhere]" title={user.username}>{user.username}</span>
                      {user.id === context.auth.user?.id && <span className="shrink-0 text-xs font-normal text-accent-muted">{t("you")}</span>}
                    </span>
                  </td>
                  <td className="col-start-2 row-start-1 lg:px-3 lg:py-2.5">
                    <select
                      aria-label={t("Role for {{name}}", { name: user.username })}
                      value={t(user.role === "admin" ? "Administrator" : "User")}
                      disabled={pendingId === user.id}
                      onChange={(event) => void updateUser(user, { role: event.target.value as PanelUserRole })}
                      className="h-9 rounded-md border border-neutral-700 bg-neutral-950 px-2 text-sm text-neutral-200 outline-none transition focus:border-accent disabled:opacity-60"
                    >
                      {roles.map((role) => <option key={role} value={role}>{t(role === "admin" ? "Administrator" : "User")}</option>)}
                    </select>
                  </td>
                  <td className="col-start-1 row-start-2 min-w-0 text-xs text-neutral-500 lg:px-3 lg:py-2.5 lg:text-sm">
                    <span className="mr-1 lg:hidden">{t("Registered")}</span>
                    <time dateTime={user.created_at}>{formatRegistrationDate(user.created_at)}</time>
                  </td>
                  <td className="col-start-2 row-start-2 text-right lg:px-3 lg:py-2.5">
                    <button
                      type="button"
                      aria-label={t("Delete {{name}}", { name: user.username })}
                      title={t("Delete {{name}}", { name: user.username })}
                      disabled={pendingId === user.id}
                      onClick={() => void deleteUser(user)}
                      className="inline-flex h-9 w-9 items-center justify-center gap-2 rounded-md text-sm text-neutral-500 transition hover:bg-red-950/30 hover:text-red-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60 lg:w-auto lg:px-2"
                    >
                      {pendingId === user.id ? <CircleNotch className="animate-spin" size={18} aria-label={t("Deleting")} /> : <Trash size={18} aria-hidden="true" />}
                      <span className="hidden lg:inline">{t("Delete")}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function formatRegistrationDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : formatDate(date);
}

function StatusMessage({ tone, message }: { tone: "loading" | "empty"; message: string }) {
  const { t } = useTranslation();
  const icon = tone === "loading" ? <CircleNotch className="animate-spin" size={18} aria-hidden="true" /> : <WarningCircle size={18} aria-hidden="true" />;
  const color = "text-neutral-500";
  return <div className={`flex items-center gap-2 py-3 text-sm ${color}`}>{icon}{message}</div>;
}
