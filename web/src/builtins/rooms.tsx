import { useTranslation } from "react-i18next";
import { t } from "../i18n";
import { ArrowLeft } from "@phosphor-icons/react/ArrowLeft";
import { Door } from "@phosphor-icons/react/Door";
import { Plus } from "@phosphor-icons/react/Plus";
import { SlidersHorizontal } from "@phosphor-icons/react/SlidersHorizontal";
import { Trash } from "@phosphor-icons/react/Trash";
import { X } from "@phosphor-icons/react/X";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  DeviceCard,
  type Device,
  type Control,
  type StateValue,
} from "./device-card";

export type Room = { id: string; name: string; device_count: number };
const button =
  "inline-flex items-center justify-center gap-2 rounded-md border border-neutral-700 px-3 py-2 text-sm hover:bg-neutral-800 focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-40";
const input =
  "w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent";

export default function RoomsView({
  rooms,
  devices,
  admin,
  pending,
  devicePending,
  api,
  perform,
  editDevice,
  send,
}: {
  rooms: Room[];
  devices: Device[];
  admin: boolean;
  pending: boolean;
  devicePending: Set<string>;
  api: (path: string, method?: string, body?: unknown) => Promise<unknown>;
  perform: (
    action: () => Promise<unknown>,
    success?: string,
  ) => Promise<boolean>;
  editDevice: (device: Device) => void;
  send: (
    device: Device,
    control: Control,
    value: StateValue,
  ) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const [current, setCurrent] = useState<string | null>(null);
  const [editor, setEditor] = useState<Room | "new" | null>(null);
  const [removing, setRemoving] = useState<Room | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const modalOpen = editor !== null || removing !== null;
  useEffect(() => {
    if (!modalOpen) return;
    const origin = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      origin?.focus();
    };
  }, [modalOpen]);
  const room = rooms.find((room) => room.id === current);
  const members = devices.filter((device) =>
    current === "" ? !device.room_id : device.room_id === current,
  );
  function openEditor(room: Room | "new") {
    setSelected(
      new Set(
        room === "new"
          ? []
          : devices
              .filter((device) => device.room_id === room.id)
              .map((device) => device.id),
      ),
    );
    setSearch("");
    setEditor(room);
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = new FormData(event.currentTarget).get("name");
    let saved: Room | undefined;
    if (
      await perform(
        async () => {
          saved = (await api(
            editor === "new" ? "rooms" : `rooms/${(editor as Room).id}`,
            editor === "new" ? "POST" : "PUT",
            { name, device_ids: [...selected] },
          )) as Room;
        },
        editor === "new" ? t("Room created") : t("Room saved"),
      )
    ) {
      setEditor(null);
      setCurrent(saved!.id);
    }
  }
  return (
    <div className="space-y-3">
      {current !== null && (
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <button
              className={button}
              aria-label={t("Back to rooms")}
              onClick={() => setCurrent(null)}
            >
              <ArrowLeft size={16} />
            </button>
            <h2 className="truncate font-brand font-semibold">
              {room?.name ?? (current === "" ? t("Unassigned") : t("Room removed"))}
            </h2>
            {room && admin && (
              <>
                <button
                  className={button}
                  aria-label={t("Edit {{name}}", { name: room.name })}
                  disabled={pending}
                  onClick={() => openEditor(room)}
                >
                  <SlidersHorizontal size={16} />
                </button>
                <button
                  className={button}
                  aria-label={t("Delete {{name}}", { name: room.name })}
                  disabled={pending}
                  onClick={() => setRemoving(room)}
                >
                  <Trash size={16} />
                </button>
              </>
            )}
          </div>
        </div>
      )}
      {current === null ? (
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {[
            ...rooms,
            {
              id: "",
              name: t("Unassigned"),
              device_count: devices.filter((device) => !device.room_id).length,
            },
          ].map((room) => (
            <button
              key={room.id}
              onClick={() => setCurrent(room.id)}
              className="flex min-w-0 items-center gap-3 rounded-lg bg-neutral-900/50 p-3 text-left hover:bg-neutral-900 focus-visible:outline-2 focus-visible:outline-accent"
            >
              <Door size={24} className="shrink-0 text-accent-muted" />
              <span className="min-w-0 flex-1 truncate font-brand font-semibold">
                {room.name}
              </span>
              <span
                className="text-sm tabular-nums text-neutral-500"
                aria-label={t("{{count}} devices", { count: room.device_count })}
              >
                {room.device_count}
              </span>
            </button>
          ))}
          {admin && (
            <button
              className="flex min-h-12 items-center gap-3 rounded-lg bg-accent/10 p-3 text-left text-sm font-medium text-accent-muted hover:bg-accent/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40"
              disabled={pending}
              onClick={() => openEditor("new")}
            >
              <Plus size={24} aria-hidden="true" />{t("Add room")}</button>
          )}
        </div>
      ) : !members.length ? (
        <p className="py-4 text-sm text-neutral-500">{t("No devices")}</p>
      ) : (
        <div className="device-card-list">
          {members.map((device) => (
            <DeviceCard
              key={device.id}
              device={device}
              pending={devicePending.has(device.id)}
              edit={() => editDevice(device)}
              send={(control, value) => send(device, control, value)}
            />
          ))}
        </div>
      )}
      {modalOpen && (
        <dialog
          ref={dialogRef}
          aria-label={
            editor
              ? editor === "new"
                ? t("Add room")
                : t("Room settings")
              : t("Delete room")
          }
          className="fixed inset-0 m-auto max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-neutral-800 bg-neutral-950 p-4 text-neutral-100 shadow-2xl backdrop:bg-black/75"
          style={{ maxWidth: "min(32rem, calc(100vw - 2rem))" }}
          onCancel={(event) => {
            event.preventDefault();
            if (!pending) {
              setEditor(null);
              setRemoving(null);
            }
          }}
          onClick={(event) => {
            const bounds = event.currentTarget.getBoundingClientRect();
            if (
              event.target === event.currentTarget &&
              !pending &&
              (event.clientX < bounds.left ||
                event.clientX > bounds.right ||
                event.clientY < bounds.top ||
                event.clientY > bounds.bottom)
            ) {
              setEditor(null);
              setRemoving(null);
            }
          }}
        >
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-brand text-lg font-semibold">
              {editor
                ? editor === "new"
                  ? t("Add room")
                  : t("Room settings")
                : t("Delete room?")}
            </h2>
            <button
              className={button}
              aria-label={t("Close room dialog")}
              disabled={pending}
              onClick={() => {
                setEditor(null);
                setRemoving(null);
              }}
            >
              <X size={18} />
            </button>
          </div>
          {editor ? (
            <form onSubmit={(event) => void save(event)} className="space-y-3">
              <label className="block space-y-1 text-sm">{t("Name")}<input
                  name="name"
                  required
                  maxLength={128}
                  defaultValue={editor === "new" ? "" : editor.name}
                  className={input}
                />
              </label>
              <input
                type="search"
                aria-label={t("Find room devices")}
                placeholder={t("Find devices…")}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className={input}
              />
              <div className="max-h-64 space-y-1 overflow-y-auto">
                {devices
                  .filter((device) =>
                    `${device.name} ${device.area}`
                      .toLowerCase()
                      .includes(search.toLowerCase()),
                  )
                  .map((device) => (
                    <label
                      key={device.id}
                      className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm hover:bg-neutral-900"
                    >
                      <input
                        type="checkbox"
                        aria-label={device.name}
                        checked={selected.has(device.id)}
                        disabled={pending}
                        onChange={(event) =>
                          setSelected((previous) => {
                            const next = new Set(previous);
                            if (event.target.checked) next.add(device.id);
                            else next.delete(device.id);
                            return next;
                          })
                        }
                        className="accent-accent"
                      />
                      <span className="min-w-0 flex-1 truncate">
                        {device.name}
                      </span>
                      {device.room_id &&
                        device.room_id !==
                          (editor === "new" ? "" : editor.id) && (
                          <span className="max-w-[40%] truncate text-xs text-neutral-500">
                            {device.area}
                          </span>
                        )}
                    </label>
                  ))}
              </div>
              <button
                className={`${button} w-full bg-accent text-white`}
                disabled={pending}
              >
                {pending ? t("Saving…") : t("Save")}
              </button>
            </form>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-neutral-400">{t("Delete")}{removing!.name}? Its devices will be unassigned.
              </p>
              <button
                className={`${button} w-full text-red-300`}
                disabled={pending}
                onClick={async () => {
                  if (
                    await perform(
                      () => api(`rooms/${removing!.id}`, "DELETE"),
                      t("Room deleted"),
                    )
                  ) {
                    setRemoving(null);
                    setCurrent(null);
                  }
                }}
              >
                {pending ? t("Deleting…") : t("Delete room")}
              </button>
            </div>
          )}
        </dialog>
      )}
    </div>
  );
}
