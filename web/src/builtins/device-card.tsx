import { useTranslation } from "react-i18next";
import { t, enumLabel, formatNumber } from "../i18n";
import { deviceImage } from "./device-types";
import CameraControl from "./camera-control";
import DeviceSummary from "./device-summary";
import { Question } from "@phosphor-icons/react/Question";
import { Power } from "@phosphor-icons/react/Power";
import { CircleNotch } from "@phosphor-icons/react/CircleNotch";
import { WifiSlash } from "@phosphor-icons/react/WifiSlash";
import { SlidersHorizontal } from "@phosphor-icons/react/SlidersHorizontal";
import { Check } from "@phosphor-icons/react/Check";
import { Minus } from "@phosphor-icons/react/Minus";
import { Plus } from "@phosphor-icons/react/Plus";
import { X } from "@phosphor-icons/react/X";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  powerState,
  quantize,
  rgbHue,
  colorValue,
  brightnessFraction,
  whiteValue,
  controlLabel,
  primaryMetric,
  type StateValue,
  type Control,
  type Device,
} from "./device-model";
export type { StateValue, Control, Device } from "./device-model";
const presets = [
  "#ff3838",
  "#ff9233",
  "#ffd43b",
  "#ffeaa7",
  "#8bea52",
  "#28c76f",
  "#2ddbaa",
  "#36cfff",
  "#427bff",
  "#8358ff",
  "#b197fc",
  "#ce53ed",
  "#ff67af",
  "#ffb3c6",
  "#ffffff",
];
export function Slider({
  control,
  value,
  disabled,
  send,
  label = controlLabel(control),
  emphasis = false,
}: {
  control: Control;
  value: StateValue | undefined;
  disabled: boolean;
  send: (value: StateValue) => Promise<boolean>;
  label?: string;
  emphasis?: boolean | "primary";
}) {
  const { t } = useTranslation();
  const min = control.constraints.min ?? 0,
    max = control.constraints.max ?? 100;
  const [draft, setDraft] = useState(typeof value === "number" ? value : min);
  const [edited, setEdited] = useState(false);
  const committing = useRef(false);
  useEffect(() => {
    setDraft(typeof value === 'number' ? value : min);
    setEdited(false);
  }, [value, min]);
  const commit = async () => {
    if (!edited || committing.current || draft === value) return;
    committing.current = true;
    try {
      if (!await send(draft)) {
        setDraft(typeof value === 'number' ? value : min);
        setEdited(false);
      }
    } finally {
      committing.current = false;
    }
  };
  return (
    <label className="block space-y-0.5 text-sm text-neutral-300">
      <span className="flex justify-between">
        {t(label)}
        <span
          className={
            emphasis === "primary" ? "font-brand text-3xl font-semibold tabular-nums text-neutral-100" : emphasis
              ? "font-brand text-xl font-semibold tabular-nums text-neutral-100"
              : "tabular-nums text-neutral-500"
          }
        >
          {value === undefined && !edited ? '—' : label === "Brightness"
            ? `${Math.round(brightnessFraction(draft, control.constraints) * 100)}%`
            : `${draft / 10 ** (control.constraints.scale ?? 0)} ${control.constraints.unit ?? ""}`}
        </span>
      </span>
      <input
        aria-label={t(label)}
        className="device-slider w-full accent-accent"
        type="range"
        min={control.constraints.step_origin ?? min}
        max={max}
        step={control.constraints.step ?? 1}
        value={draft}
        disabled={disabled}
        onChange={(e) => {
          setEdited(true);
          setDraft(quantize(Number(e.target.value), {min, max, step: control.constraints.step, step_origin: control.constraints.step_origin}));
        }}
        onPointerUp={commit}
        onKeyUp={commit}
        onBlur={commit}
      />
    </label>
  );
}
export function Palette({
  control,
  value,
  brightness,
  disabled,
  send,
  white,
  whiteActive = false,
}: {
  control: Control;
  value: StateValue | undefined;
  brightness: number;
  disabled: boolean;
  send: (value: StateValue) => Promise<boolean>;
  white?: () => Promise<boolean>;
  whiteActive?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false),
    [h, setH] = useState(0),
    [s, setS] = useState(1);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      triggerRef.current?.focus();
    };
  }, [open]);
  useEffect(() => {
    if (whiteActive) {
      setH(0);
      setS(0);
    } else if (typeof value === "object" && value) {
      setH((value.h * 360) / (control.constraints.h?.max || 360));
      setS(value.s / (control.constraints.s?.max || 1000));
    }
  }, [JSON.stringify(value), whiteActive]);
  const select = (hue: number, saturation: number) =>
    saturation === 0 && white ? white() : send(colorValue(control, hue, saturation, brightness));
  return (
    <div className="space-y-3">
      <div className="grid w-full max-w-[18.625rem] grid-cols-8 gap-1.5">
        {presets.map((color) => {
          const hsv = rgbHue(color);
          return (
            <button
              key={color}
              type="button"
              aria-label={t("Color {{color}}", { color })}
              disabled={disabled}
              className={`aspect-square w-full max-w-8 justify-self-center rounded-full border-2 transition hover:scale-110 focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-40 ${(color === '#ffffff' && whiteActive) || (!whiteActive && typeof value === 'object' && Math.abs(h - hsv.h) < 8 && Math.abs(s - hsv.s) < 0.08) ? "border-white" : "border-transparent"}`}
              style={{ background: color }}
              onClick={() => void (color === '#ffffff' && white ? white() : select(hsv.h, hsv.s))}
            />
          );
        })}
        <button
          ref={triggerRef}
          type="button"
          aria-label={t("Choose color")}
          aria-expanded={open}
          aria-haspopup="dialog"
          disabled={disabled}
          onClick={() => setOpen(!open)}
          className="aspect-square w-full max-w-8 justify-self-center rounded-full border-2 border-neutral-600 focus-visible:outline-2 focus-visible:outline-accent"
          style={{
            background: "conic-gradient(red,yellow,lime,cyan,blue,magenta,red)",
          }}
        />
      </div>
      {open &&
        createPortal(
          <dialog
            ref={dialogRef}
            aria-label={t("Choose color")}
            className="fixed inset-0 m-auto rounded-xl border border-neutral-800 bg-neutral-950 p-0 text-neutral-100 shadow-2xl backdrop:bg-black/65"
            style={{ width: "min(20rem, calc(100vw - 2rem))" }}
            onCancel={(event) => {
              event.preventDefault();
              setOpen(false);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") event.stopPropagation();
            }}
            onClick={(event) => {
              if (event.target === event.currentTarget) setOpen(false);
            }}
          >
            <div className="space-y-4 p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-brand font-semibold">{t("Color")}</h3>
                <button
                  type="button"
                  aria-label={t("Close color picker")}
                  onClick={() => setOpen(false)}
                  className="grid h-8 w-8 place-items-center rounded-full text-neutral-400 hover:bg-neutral-800 focus-visible:outline-2 focus-visible:outline-accent"
                >
                  <X size={18} />
                </button>
              </div>
              <div
                role="slider"
                aria-label={t("Color wheel")}
                aria-valuemin={0}
                aria-valuemax={360}
                aria-valuenow={Math.round(h)}
                aria-valuetext={t("Hue {{hue}}, saturation {{saturation}}%", { hue: Math.round(h), saturation: Math.round(s * 100) })}
                tabIndex={disabled ? -1 : 0}
                className="relative mx-auto h-44 w-44 touch-none rounded-full focus-visible:outline-2 focus-visible:outline-accent"
                style={{
                  background:
                    "radial-gradient(circle closest-side,white,transparent),conic-gradient(from 90deg,red,yellow,lime,cyan,blue,magenta,red)",
                }}
                onPointerDown={(e) => {
                  if (disabled) return;
                  e.currentTarget.setPointerCapture(e.pointerId);
                  const rect = e.currentTarget.getBoundingClientRect(),
                    x = e.clientX - rect.left - rect.width / 2,
                    y = e.clientY - rect.top - rect.height / 2;
                  setH(((Math.atan2(y, x) * 180) / Math.PI + 360) % 360);
                  setS(Math.min(1, Math.hypot(x, y) / (rect.width / 2)));
                }}
                onPointerMove={(e) => {
                  if (
                    disabled ||
                    !e.currentTarget.hasPointerCapture(e.pointerId)
                  )
                    return;
                  const rect = e.currentTarget.getBoundingClientRect(),
                    x = e.clientX - rect.left - rect.width / 2,
                    y = e.clientY - rect.top - rect.height / 2;
                  setH(((Math.atan2(y, x) * 180) / Math.PI + 360) % 360);
                  setS(Math.min(1, Math.hypot(x, y) / (rect.width / 2)));
                }}
                onKeyDown={(e) => {
                  if (disabled) return;
                  if (
                    [
                      "ArrowLeft",
                      "ArrowRight",
                      "ArrowUp",
                      "ArrowDown",
                    ].includes(e.key)
                  ) {
                    e.preventDefault();
                    if (e.key === "ArrowLeft" || e.key === "ArrowRight")
                      setH((h + (e.key === "ArrowRight" ? 5 : 355)) % 360);
                    else
                      setS(
                        Math.max(
                          0,
                          Math.min(1, s + (e.key === "ArrowUp" ? 0.05 : -0.05)),
                        ),
                      );
                  }
                }}
              >
                <span
                  className="pointer-events-none absolute h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-black outline-2 outline-white"
                  style={{
                    left: `${50 + Math.cos((h * Math.PI) / 180) * s * 50}%`,
                    top: `${50 + Math.sin((h * Math.PI) / 180) * s * 50}%`,
                  }}
                />
              </div>
              <button
                type="button"
                disabled={disabled}
                className="w-full rounded-md bg-accent py-2 text-sm"
                onClick={async () => {
                  if (await select(h, s)) setOpen(false);
                }}
              >{t("Apply color")}</button>
            </div>
          </dialog>,
          document.body,
        )}
    </div>
  );
}
export function DeviceCard({
  device,
  pending,
  edit,
  send,
}: {
  device: Device;
  pending: boolean;
  edit: () => void;
  send: (control: Control, value: StateValue) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const light =
    device.kind_override === 'dj' || (!device.kind_override && (
    ["dj", "xdd", "fwd", "dc", "dd", "gyd", "fsd"].includes(device.kind) ||
    device.controls.some((c) => c.code === "switch_led")));
  const power = device.controls.find(
    (c) =>
      c.type === "Boolean" && c.constraints.retrievable !== false &&
      [
        "switch_led",
        "switch",
        "switch_1",
        "switch_fan",
        "switch_spray",
      ].includes(c.code),
  );
  const bright = device.controls.find((c) =>
    ["bright_value_v2", "bright_value"].includes(c.code),
  );
  const color = device.controls.find(
    (c) =>
      ["colour_data_v2", "colour_data"].includes(c.code) && c.type === "Json",
  );
  const hsv = color && device.state[color.code],
    colored =
      color && device.state.work_mode === "colour" && typeof hsv === "object";
  const brightness = colored ? brightnessFraction(hsv.v, color.constraints.v!)
    : bright ? brightnessFraction(device.state[bright.code], bright.constraints) : 1;
  const white = device.controls.find(c => ['temp_value', 'temp_value_v2'].includes(c.code))
    ?? device.controls.find(c => c.code === 'work_mode' && c.type === 'Enum' && c.constraints.range?.includes('white'));
  const brightnessControl = colored ? { ...color, type: 'Integer' as const, constraints: color.constraints.v! } : bright;
  const disabled = pending || !device.available || !device.enabled;
  const powered = power ? powerState(device, power.code) : undefined;
  const main = device.controls.filter(control => control !== power &&
    !(light && [bright, color, white].includes(control)) &&
    !(light && ['temp_value', 'temp_value_v2', 'color_scene'].includes(control.code)) &&
    !(light && control.code === 'work_mode' && control.constraints.range?.some(mode => ['white', 'colour', 'scene'].includes(mode))));
  return (
    <article aria-busy={pending} className="space-y-2 rounded-xl border border-neutral-800 bg-neutral-900/30 p-3 sm:px-4">
      <div className="flex items-center gap-3">
        <img src={deviceImage(device)} alt="" className="h-12 w-12 shrink-0 object-contain" />
        <h2
          className="min-w-0 flex-1 truncate font-brand font-semibold"
          title={device.name}
        >
          {device.name}
        </h2>
        {power && (
          <button
            type="button"
            role={powered === undefined ? "button" : "switch"}
            aria-label={t("{{name}} power", { name: device.name })}
            aria-checked={powered}
            aria-busy={pending}
            title={pending ? t('Updating device') : !device.enabled ? t('Disabled') : device.state_stale ? t('State unknown') : !device.available ? t('Offline') : powered === undefined ? t("State unknown") : t('{{name}} power', { name: device.name })}
            disabled={disabled}
            onClick={() => void send(power, device.state[power.code] !== true)}
            className={`grid h-12 w-12 shrink-0 place-items-center rounded-full transition focus-visible:outline-2 focus-visible:outline-accent ${pending ? "disabled:opacity-100" : "disabled:opacity-40"} ${powered === true ? "bg-accent text-white shadow-lg shadow-accent/20" : "bg-neutral-800 text-neutral-500"}`}
          >
            {pending ? <CircleNotch size={25} weight="bold" className={`animate-spin motion-reduce:animate-none ${powered === true ? 'text-white' : 'text-accent-muted'}`} aria-label={t('Updating device')} /> : device.state_stale ? <Question size={25} aria-label={t("State unknown")} /> : !device.available ? <WifiSlash size={25} aria-label={t(device.enabled ? 'Offline' : 'Disabled')} /> : powered === undefined ? <Question size={25} aria-label={t("State unknown")} /> : <Power size={25} weight="bold" />}
          </button>
        )}
        {!power && (pending || !device.available || device.state_stale) && <span role="status" title={t(pending ? 'Updating device' : !device.enabled ? 'Disabled' : device.state_stale ? 'State unknown' : 'Offline')} className="grid h-8 w-8 shrink-0 place-items-center text-neutral-500">
          {pending ? <CircleNotch size={22} className="animate-spin motion-reduce:animate-none text-accent-muted" aria-label={t('Updating device')} /> : device.state_stale ? <Question size={22} aria-label={t("State unknown")} /> : <WifiSlash size={22} aria-label={t(device.enabled ? 'Offline' : 'Disabled')} />}
        </span>}
        <button
          type="button"
          aria-label={t("Edit {{name}}", { name: device.name })}
          onClick={edit}
          className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-neutral-500 hover:bg-neutral-800 hover:text-white focus-visible:outline-2 focus-visible:outline-accent"
        >
          <SlidersHorizontal size={18} />
        </button>
      </div>
      {light && brightnessControl && (
        <Slider
          control={brightnessControl}
          value={
            colored ? hsv.v : device.state[bright!.code]
          }
          disabled={disabled}
          send={(value) =>
            colored
              ? send(color!, {
                  ...hsv,
                  v: quantize(Number(value), color!.constraints.v!),
                })
              : send(bright!, value)
          }
          label="Brightness"
          emphasis
        />
      )}
      {light && device.controls.filter((c) => ["temp_value", "temp_value_v2", "color_scene"].includes(c.code)).map((control) => (
        <CompactControl key={control.code} control={control} value={device.state[control.code]} disabled={disabled} send={(value) => send(control, value)} />
      ))}
      {light && color && (
        <Palette
          control={color}
          value={device.state[color.code]}
          brightness={brightness}
          white={white ? () => send(white, white.type === 'Enum' ? 'white' : whiteValue(white)) : undefined}
          whiteActive={device.state.work_mode === 'white'}
          disabled={disabled}
          send={(value) => send(color, value)}
        />
      )}

      {!light && <DeviceSummary device={device} displayedControls={[...(power ? [power] : []), ...main]} />}
      {main.map((c) => (
          <CompactControl
            key={c.code}
            control={c}
            value={device.state[c.code]}
            emphasis={primaryMetric(device)?.code === c.code || (c.code === 'percent_control' && primaryMetric(device)?.code === 'percent_state' && device.state.percent_state === device.state.percent_control)}
            disabled={disabled}
            send={(value) => send(c, value)}
          />
        ))}
    </article>
  );
}
function NumberControl({ control, value, disabled, send }: {
  control: Control; value: StateValue | undefined; disabled: boolean; send: (value: StateValue) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const fieldId = useId();
  const scale = 10 ** (control.constraints.scale ?? 0);
  const [draft, setDraft] = useState(typeof value === 'number' ? String(value / scale) : '');
  useEffect(() => setDraft(typeof value === 'number' ? String(value / scale) : ''), [value, scale]);
  return <form className="flex items-center justify-between gap-2 text-sm" onSubmit={event => {
    event.preventDefault();
    if (!draft.trim() || !Number.isFinite(Number(draft))) return;
    const next = quantize(Math.round(Number(draft) * scale), { min: control.constraints.min!, max: control.constraints.max!, step: control.constraints.step, step_origin: control.constraints.step_origin });
    if (next !== value) void send(next);
  }}><label htmlFor={fieldId}>{t(controlLabel(control))}</label><div className="flex items-center gap-1">
    <input id={fieldId} aria-label={t(controlLabel(control))} type="number" required step={(control.constraints.step ?? 1) / scale}
      value={draft} disabled={disabled} onChange={event => setDraft(event.target.value)} className="w-20 rounded-md border border-neutral-700 bg-neutral-950 px-2 py-1.5" />
    <span className="text-neutral-500">{control.constraints.unit}</span><button disabled={disabled} aria-label={t('Apply')}><Check size={18} /></button>
  </div></form>;
}
export function CompactControl({
  control,
  value,
  disabled,
  send,
  emphasis = false,
}: {
  control: Control;
  value: StateValue | undefined;
  disabled: boolean;
  send: (value: StateValue) => Promise<boolean>;
  emphasis?: boolean;
}) {
  const { t } = useTranslation();
  if (control.code === 'video_stream') return <CameraControl value={value} disabled={disabled} send={() => send('hls')} />;
  if (control.constraints.relative) return <div className="flex items-center justify-between gap-2 text-sm">
    <span>{t(controlLabel(control))}</span><div className="flex gap-2">
      <button disabled={disabled} aria-label={t('Decrease {{name}}', { name: t(controlLabel(control)) })} className="rounded-full bg-neutral-800 p-2 disabled:opacity-40" onClick={() => void send(-(control.constraints.step ?? 1))}><Minus size={18} /></button>
      <button disabled={disabled} aria-label={t('Increase {{name}}', { name: t(controlLabel(control)) })} className="rounded-full bg-neutral-800 p-2 disabled:opacity-40" onClick={() => void send(control.constraints.step ?? 1)}><Plus size={18} /></button>
    </div></div>;
  if (control.type === 'Integer' && control.constraints.unbounded) return <NumberControl control={control} value={value} disabled={disabled} send={send} />;
  if (control.type === 'Boolean' && control.constraints.retrievable === false) return <div className="flex items-center justify-between gap-2 text-sm"><span>{t(controlLabel(control))}</span><div className="flex gap-2">{[true, false].map(on => <button key={String(on)} disabled={disabled} className="rounded-md bg-neutral-800 px-3 py-1 disabled:opacity-40" onClick={() => void send(on)}>{t(on ? 'On' : 'Off')}</button>)}</div></div>;
  if (control.type === "Integer")
    return (
      <Slider control={control} value={value} disabled={disabled} send={send} emphasis={emphasis ? "primary" : false} />
    );
  if (control.type === "Json")
    return (
      <Palette
        control={control}
        value={value}
        brightness={
          typeof value === "object"
            ? value.v / (control.constraints.v?.max || 1000)
            : 1
        }
        disabled={disabled}
        send={send}
      />
    );
  if (control.type === "Boolean")
    return (
      <div className="flex items-center justify-between text-sm">
        <span>{t(controlLabel(control))}</span>
        <button
          type="button"
          disabled={disabled}
          role={typeof value === "boolean" ? "switch" : "button"}
          aria-label={t(controlLabel(control))}
          aria-checked={typeof value === "boolean" ? value : undefined}
          className={`rounded-md px-3 py-1 ${value === true ? "bg-accent" : "bg-neutral-800"}`}
          onClick={() => void send(value !== true)}
        >
          {typeof value !== "boolean" ? t("State unknown") : value ? t("On") : t("Off")}
        </button>
      </div>
    );
  return (
    <label className="flex items-center justify-between gap-3 text-sm">
      {t(controlLabel(control))}
      <select
        aria-label={t(controlLabel(control))}
        className="max-w-[60%] rounded-md border border-neutral-700 bg-neutral-950 px-2 py-1.5"
        value={typeof value === "string" ? value : ""}
        disabled={disabled}
        onChange={(e) => void send(e.target.value)}
      >
        <option value="" disabled>{t("Select")}</option>
        {control.constraints.range?.map((mode) => (
          <option key={mode} value={mode}>
            {enumLabel(mode)}
          </option>
        ))}
      </select>
    </label>
  );
}
