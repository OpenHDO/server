import { useEffect, useState } from "react";

import { Check } from "@phosphor-icons/react/Check";
import { CircleNotch } from "@phosphor-icons/react/CircleNotch";
import { Trash } from "@phosphor-icons/react/Trash";
import { WarningCircle } from "@phosphor-icons/react/WarningCircle";
import type { PanelAuthUser, PanelModuleContext, PanelUserRole } from "../modules/registry";

const roles: PanelUserRole[] = ["user", "admin"];
const registrationDate = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

type RequestError = { detail?: string };

async function readError(response: Response) {
  const payload = (await response.json().catch(() => null)) as RequestError | null;
  return payload?.detail ?? `Request failed (${response.status})`;
}

export default function UsersView({ context }: { context: PanelModuleContext }) {
  const [users, setUsers] = useState<PanelAuthUser[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  async function loadUsers() {
    setLoadState("loading");
    setLoadError(null);
    try {
      const response = await context.api.request("/api/v1/admin/users");
      if (!response.ok) throw new Error(await readError(response));
      const payload = (await response.json()) as { users: PanelAuthUser[] };
      setUsers(payload.users);
      setLoadState("ready");
    } catch (error) {
      setLoadState("error");
      setLoadError(error instanceof Error ? error.message : "Unable to load users");
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
      if (!response.ok) throw new Error(await readError(response));
      const updated = (await response.json()) as PanelAuthUser;
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSuccess("User updated");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to update user");
    } finally {
      setPendingId(null);
    }
  }

  async function deleteUser(user: PanelAuthUser) {
    if (!window.confirm(`Delete ${user.username}?`)) return;
    setPendingId(user.id);
    setActionError(null);
    setSuccess(null);
    try {
      const response = await context.api.request(`/api/v1/admin/users/${user.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await readError(response));
      setUsers((current) => current.filter((item) => item.id !== user.id));
      setSuccess("User deleted");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to delete user");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      {actionError && <StatusMessage tone="error" message={actionError} />}
      {success && <StatusMessage tone="success" message={success} />}

      {loadState === "loading" && <StatusMessage tone="loading" message="Loading users" />}
      {loadState === "error" && (
        <div className="flex items-center justify-between gap-4 border-y border-red-900/70 py-4 text-sm text-red-300">
          <span className="inline-flex items-center gap-2"><WarningCircle size={18} aria-hidden="true" />{loadError}</span>
          <button type="button" onClick={() => void loadUsers()} className="text-accent-muted underline underline-offset-4">Retry</button>
        </div>
      )}
      {loadState === "ready" && users.length === 0 && <StatusMessage tone="empty" message="No users" />}
      {loadState === "ready" && users.length > 0 && (
        <div className="overflow-x-auto border-y border-neutral-800">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="border-b border-neutral-800 text-xs uppercase tracking-wide text-neutral-500">
              <tr>
                <th scope="col" className="px-3 py-3 font-medium">User</th>
                <th scope="col" className="px-3 py-3 font-medium">Role</th>
                <th scope="col" className="px-3 py-3 font-medium">Registered</th>
                <th scope="col" className="px-3 py-3 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              {users.map((user) => (
                <tr key={user.id}>
                  <td className="px-3 py-4 font-medium text-neutral-100">
                    <span className="inline-flex items-center gap-2">
                      {user.username}
                      {user.id === context.auth.user?.id && <span className="text-xs font-normal text-accent-muted">you</span>}
                    </span>
                  </td>
                  <td className="px-3 py-4">
                    <select
                      aria-label={`Role for ${user.username}`}
                      value={user.role}
                      disabled={pendingId === user.id}
                      onChange={(event) => void updateUser(user, { role: event.target.value as PanelUserRole })}
                      className="h-9 rounded-md border border-neutral-700 bg-neutral-950 px-2 text-sm text-neutral-200 outline-none transition focus:border-accent disabled:opacity-60"
                    >
                      {roles.map((role) => <option key={role}>{role}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-4 text-neutral-400">
                    <time dateTime={user.created_at}>{formatRegistrationDate(user.created_at)}</time>
                  </td>
                  <td className="px-3 py-4 text-right">
                    <button
                      type="button"
                      aria-label={`Delete ${user.username}`}
                      title={`Delete ${user.username}`}
                      disabled={pendingId === user.id}
                      onClick={() => void deleteUser(user)}
                      className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-red-900/70 px-3 text-sm text-red-300 transition hover:border-red-700 hover:text-red-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60"
                    >
                      {pendingId === user.id ? <CircleNotch className="animate-spin" size={18} aria-label="Deleting" /> : <Trash size={18} aria-hidden="true" />}
                      <span>Delete</span>
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
  return Number.isNaN(date.getTime()) ? value : registrationDate.format(date);
}

function StatusMessage({ tone, message }: { tone: "loading" | "empty" | "error" | "success"; message: string }) {
  const icon = tone === "loading" ? <CircleNotch className="animate-spin" size={18} aria-hidden="true" /> : tone === "success" ? <Check size={18} aria-hidden="true" /> : <WarningCircle size={18} aria-hidden="true" />;
  const color = tone === "error" ? "text-red-300" : tone === "success" ? "text-accent-muted" : "text-neutral-500";
  return <div className={`flex items-center gap-2 border-y border-neutral-800 py-4 text-sm ${color}`}>{icon}{message}</div>;
}
