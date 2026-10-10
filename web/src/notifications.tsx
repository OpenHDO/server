import { useTranslation } from "react-i18next";
import { t } from "./i18n";
import { CheckCircle } from "@phosphor-icons/react/CheckCircle";
import { WarningCircle } from "@phosphor-icons/react/WarningCircle";
import { X } from "@phosphor-icons/react/X";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { addNotice, type Notice } from "./notifications-state";

type Notify = (
  tone: Notice["tone"],
  message: string,
  action?: Notice["action"],
) => void;
const Notifications = createContext<Notify>(() => {});
export const useNotifications = () => useContext(Notifications);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [notices, setNotices] = useState<Notice[]>([]);
  const [host, setHost] = useState<Element>(document.body);
  const nextId = useRef(0);
  const viewport = useRef<HTMLDivElement>(null);
  const notify = useCallback<Notify>((tone, message, action) => {
    const notice = { id: ++nextId.current, tone, message, action };
    setNotices((current) => addNotice(current, notice));
  }, []);
  const dismiss = useCallback(
    (id: number) =>
      setNotices((current) => current.filter((notice) => notice.id !== id)),
    [],
  );
  const visible = notices.length > 0;
  useEffect(() => {
    if (!visible) return;
    // Native dialogs make the rest of the document inert; keep notifications interactive above them.
    const chooseHost = () =>
      setHost(
        [...document.querySelectorAll("dialog[open]")].at(-1) ?? document.body,
      );
    chooseHost();
    const observer = new MutationObserver(chooseHost);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["open"],
    });
    return () => observer.disconnect();
  }, [visible]);
  useEffect(() => {
    if (
      visible &&
      viewport.current &&
      !viewport.current.matches(":popover-open")
    )
      viewport.current.showPopover();
  }, [visible, host]);
  return (
    <Notifications.Provider value={notify}>
      {children}
      {visible &&
        createPortal(
          <div
            ref={viewport}
            popover="manual"
            className="pointer-events-none space-y-2"
            style={{
              position: "fixed",
              top: "max(12px, env(safe-area-inset-top))",
              right: 12,
              bottom: "auto",
              left: "auto",
              margin: 0,
              padding: 0,
              border: 0,
              background: "transparent",
              overflow: "visible",
              width: "min(360px, calc(100vw - 24px))",
            }}
          >
            {notices.map((notice) => (
              <Notification key={notice.id} notice={notice} dismiss={dismiss} />
            ))}
          </div>,
          host,
        )}
    </Notifications.Provider>
  );
}

function Notification({
  notice,
  dismiss,
}: {
  notice: Notice;
  dismiss: (id: number) => void;
}) {
  const { t } = useTranslation();
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused || notice.action) return;
    const timer = window.setTimeout(
      () => dismiss(notice.id),
      notice.tone === "error" ? 9000 : 4500,
    );
    return () => window.clearTimeout(timer);
  }, [notice.id, notice.tone, notice.action, paused, dismiss]);
  const Icon = notice.tone === "error" ? WarningCircle : CheckCircle;
  return (
    <div
      role={notice.tone === "error" ? "alert" : "status"}
      aria-atomic="true"
      className={`pointer-events-auto flex items-start gap-3 rounded-xl border bg-neutral-950 p-3 text-sm text-neutral-100 shadow-xl ${notice.tone === "error" ? "border-red-900" : "border-accent/50"}`}
      onPointerEnter={() => setPaused(true)}
      onPointerLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget))
          setPaused(false);
      }}
    >
      <Icon
        size={21}
        className={`mt-0.5 shrink-0 ${notice.tone === "error" ? "text-red-400" : "text-accent-muted"}`}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1 break-words">
        <p>{t(notice.message)}</p>
        {notice.action && (
          <button
            className="mt-2 text-accent-muted underline underline-offset-4"
            onClick={() => {
              dismiss(notice.id);
              notice.action!.onClick();
            }}
          >
            {t(notice.action.label)}
          </button>
        )}
      </div>
      <button
        type="button"
        aria-label={t("Dismiss notification")}
        className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-neutral-500 hover:bg-neutral-800 focus-visible:outline-2 focus-visible:outline-accent"
        onClick={() => dismiss(notice.id)}
      >
        <X size={16} />
      </button>
    </div>
  );
}
