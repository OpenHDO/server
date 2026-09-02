import { useEffect, useState } from "react";

import { Check } from "@phosphor-icons/react/Check";
import { CircleNotch } from "@phosphor-icons/react/CircleNotch";
import { WarningCircle } from "@phosphor-icons/react/WarningCircle";
import type { PanelAuthUser, PanelModuleContext, PanelUserRole } from "../modules/registry";

const roles: PanelUserRole[] = ["admin", "operator", "viewer"];

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
  const [updatingId, setUpdatingId] = useState<string | null>(null);

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

  async function updateUser(user: PanelAuthUser, change: Partial<Pick<PanelAuthUser, "role" | "active">>) {
    setUpdatingId(user.id);
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
      setUpdatingId(null);
    }
  }

  return (
    <div className="max-w-4xl space-y-10">
      <div className="flex items-center justify-between gap-4 border-b border-neutral-800 pb-4">
        <h1 className="font-brand text-2xl font-bold tracking-tight">Users</h1>
        <span className="text-sm text-neutral-500">{context.auth.user?.username}</span>
      </div>

      {actionError && <StatusMessage tone="error" message={actionError} />}
      {success && <StatusMessage tone="success" message={success} />}

      <section>
        <h2 className="sr-only">Registered users</h2>
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
                  <th scope="col" className="px-3 py-3 font-medium">Status</th>
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
                        disabled={updatingId === user.id}
                        onChange={(event) => void updateUser(user, { role: event.target.value as PanelUserRole })}
                        className="h-9 rounded-md border border-neutral-700 bg-neutral-950 px-2 text-sm text-neutral-200 outline-none transition focus:border-accent disabled:opacity-60"
                      >
                        {roles.map((role) => <option key={role}>{role}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-4 text-neutral-400">{user.active ? "Active" : "Disabled"}</td>
                    <td className="px-3 py-4 text-right">
                      <button
                        type="button"
                        disabled={updatingId === user.id}
                        onClick={() => void updateUser(user, { active: !user.active })}
                        className="h-9 rounded-md border border-neutral-700 px-3 text-sm text-neutral-300 transition hover:border-neutral-500 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60"
                      >
                        {updatingId === user.id ? <CircleNotch className="animate-spin" size={18} aria-label="Updating" /> : user.active ? "Disable" : "Enable"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function StatusMessage({ tone, message }: { tone: "loading" | "empty" | "error" | "success"; message: string }) {
  const icon = tone === "loading" ? <CircleNotch className="animate-spin" size={18} aria-hidden="true" /> : tone === "success" ? <Check size={18} aria-hidden="true" /> : <WarningCircle size={18} aria-hidden="true" />;
  const color = tone === "error" ? "text-red-300" : tone === "success" ? "text-accent-muted" : "text-neutral-500";
  return <div className={`flex items-center gap-2 border-y border-neutral-800 py-4 text-sm ${color}`}>{icon}{message}</div>;
}
