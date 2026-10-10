import { useTranslation } from "react-i18next";
import { t } from "../i18n";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNotifications } from "../notifications";

type Login = { id: string; qr_image: string; expires_in: number };
type Result = { status: "pending" | "connected"; integration_id: string | null };
const button = "rounded-md border border-neutral-700 px-3 py-2 text-sm hover:border-neutral-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40";
const input = "w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent";

export default function TuyaLogin({ request, integration, connected, back }: {
  request: (path: string, method?: string, body?: unknown) => Promise<unknown>;
  integration: { id: string; name: string } | null;
  connected: () => void;
  back: () => void;
}) {
  const { t } = useTranslation();
  const notify = useNotifications();
  const [session, setSession] = useState<Login | null>(null);
  const [busy, setBusy] = useState(false);
  const [remaining, setRemaining] = useState(0);
  const [polling, setPolling] = useState(true);
  const [name, setName] = useState(integration?.name ?? "Tuya");
  const [userCode, setUserCode] = useState("");
  const mounted = useRef(true);
  const checking = useRef(false);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const codeInput = useRef<HTMLInputElement>(null);
  const sessionId = useRef<string | null>(null);
  sessionId.current = session?.id ?? null;
  const callbacks = useRef({ request, connected });
  callbacks.current = { request, connected };
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    if (!session) return;
    confirmButton.current?.focus();
    const deadline = Date.now() + session.expires_in * 1000;
    const timer = window.setInterval(() => {
      const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setRemaining(seconds);
      if (!seconds) {
        window.clearInterval(timer);
        setPolling(false);
        notify("error", t("QR code expired. Start sign-in again."));
      }
    }, 1000);
    return () => {
      window.clearInterval(timer);
      void callbacks.current.request(`integrations/tuya/login/${session.id}`, "DELETE").catch(() => {});
    };
  }, [session, notify]);

  async function check(manual = false) {
    if (!session || checking.current || remaining <= 0) return;
    const id = session.id;
    checking.current = true;
    if (manual) setBusy(true);
    try {
      const result = await callbacks.current.request(`integrations/tuya/login/${session.id}`, "POST") as Result;
      if (!mounted.current || sessionId.current !== id) return;
      if (result.status === "connected") {
        setPolling(false);
        notify("success", t("Tuya account connected"));
        callbacks.current.connected();
      } else if (manual) {
        notify("error", t("Scan the QR code and confirm sign-in in Tuya Smart or Smart Life."));
        setPolling(true);
      }
    } catch (reason) {
      if (mounted.current && sessionId.current === id) {
        setPolling(false);
        notify("error", reason instanceof Error ? reason.message : t("Unable to sign in to Tuya"));
      }
    } finally {
      checking.current = false;
      if (mounted.current && sessionId.current === id) {
        setBusy(false);
        if (manual) window.requestAnimationFrame(() => confirmButton.current?.focus());
      }
    }
  }
  const checkRef = useRef(check);
  checkRef.current = check;
  useEffect(() => {
    if (!session || !polling) return;
    const timer = window.setInterval(() => void checkRef.current(), 3000);
    return () => window.clearInterval(timer);
  }, [session, polling]);

  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const result = await request("integrations/tuya/login", "POST", {
        name: name.trim(), user_code: userCode.trim(), integration_id: integration?.id ?? null,
      }) as Login;
      if (!mounted.current) {
        void request(`integrations/tuya/login/${result.id}`, "DELETE").catch(() => {});
        return;
      }
      setRemaining(result.expires_in);
      setPolling(true);
      setSession(result);
    } catch (reason) {
      if (mounted.current) notify("error", reason instanceof Error ? reason.message : t("Unable to start Tuya sign-in"));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return session ? (
    <div className="space-y-3">
      <div className="mx-auto w-fit rounded-lg bg-white p-2">
        <img src={session.qr_image} alt={t("Tuya account sign-in QR code")} className="h-56 w-56 max-w-full" />
      </div>
      <p className="text-center text-sm text-neutral-400">{t("Scan in Tuya Smart or Smart Life and confirm sign-in.")}</p>
      <p className="text-center text-xs tabular-nums text-neutral-500">
        {remaining > 0 ? `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` : t("QR code expired")}
      </p>
      <div className="flex justify-end gap-2">
        <button className={button} disabled={busy} onClick={() => { setSession(null); window.requestAnimationFrame(() => codeInput.current?.focus()); }}>{t("New QR code")}</button>
        <button ref={confirmButton} className={`${button} bg-accent font-semibold text-neutral-950`} disabled={busy || remaining <= 0} onClick={() => void check(true)}>
          {busy ? t("Checking…") : t("I've confirmed")}
        </button>
      </div>
    </div>
  ) : (
    <form onSubmit={(event) => void start(event)} className="space-y-3">
      <label className="block space-y-1 text-sm">{t("Name")}<input className={input} required maxLength={128} value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <label className="block space-y-1 text-sm">{t("User Code")}<input ref={codeInput} className={input} required maxLength={128} autoComplete="off" spellCheck={false} value={userCode} onChange={(event) => setUserCode(event.target.value)} aria-describedby="tuya-user-code-help" />
      </label>
      <p id="tuya-user-code-help" className="text-xs text-neutral-500">{t("Tuya Smart / Smart Life → Me → Settings → Account and Security → User Code.")}</p>
      <div className="flex justify-end gap-2">
        {!integration && <button type="button" className={button} disabled={busy} onClick={back}>{t("Back")}</button>}
        <button className={`${button} bg-accent font-semibold text-neutral-950`} disabled={busy}>{busy ? t("Opening…") : integration ? t("Sign in again") : t("Sign in")}</button>
      </div>
    </form>
  );
}
