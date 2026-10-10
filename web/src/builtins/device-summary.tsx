import { useTranslation } from "react-i18next";
import { t, metricText } from "../i18n";
import { Fan } from "@phosphor-icons/react/Fan";
import { Lightning } from "@phosphor-icons/react/Lightning";
import { Drop } from "@phosphor-icons/react/Drop";
import { ShieldCheck } from "@phosphor-icons/react/ShieldCheck";
import { Robot } from "@phosphor-icons/react/Robot";
import { Warning } from "@phosphor-icons/react/Warning";
import {
  summaryMetrics,
  type Control,
  type Device,
} from "./device-model";

export default function DeviceSummary({ device, displayedControls = [] }: { device: Device; displayedControls?: Control[] }) {
  const { t } = useTranslation();
  const { primary, secondary } = summaryMetrics(device, displayedControls);
  const muted = !device.available || !device.enabled || device.state_stale;
  if (!primary && !secondary.length) return null;
  const temperature =
    [
      "temp_current",
      "temp_current_f",
      "temperature",
      "temp_set",
      "temp_set_f",
    ].includes(primary?.code ?? "") && primary?.number !== null;
  const curtain =
    ["cl", "clkg"].includes(device.kind) && primary?.number !== null;
  const min = primary?.min ?? (primary?.unit === "°C" ? -10 : 0),
    max = primary?.max ?? (primary?.unit === "°C" ? 50 : 100);
  const fraction = Math.max(
    0,
    Math.min(1, ((primary?.number ?? min) - min) / (max - min || 1)),
  );
  const angle = Math.PI * (1 - fraction),
    markerX = 100 + 80 * Math.cos(angle),
    markerY = 94 - 80 * Math.sin(angle);
  const Icon =
    primary?.severity ? Warning : device.kind === "fs"
      ? Fan
      : primary?.code.startsWith("cur_")
        ? Lightning
        : ["pir", "mcs", "ywbj", "rqbj", "sj"].includes(device.kind)
          ? ShieldCheck
          : device.kind === "sd"
            ? Robot
            : primary?.code.startsWith("switch")
              ? Lightning
              : Drop;
  return (
    <div className={`flex items-center gap-3 ${muted ? "opacity-45" : ""}`}>
      {primary && <div className="min-w-0 flex-1">
        {temperature ? (
          <div className="relative mx-auto max-w-52 pt-1">
            <svg viewBox="0 0 200 116" className="w-full" aria-hidden="true">
              <path
                d="M20 94 A80 80 0 0 1 180 94"
                fill="none"
                stroke="#262626"
                strokeWidth="9"
                strokeLinecap="round"
              />
              <path
                d="M20 94 A80 80 0 0 1 180 94"
                fill="none"
                stroke={muted ? "#737373" : "#70d6a2"}
                strokeWidth="9"
                strokeLinecap="round"
                pathLength="100"
                strokeDasharray={`${fraction * 100} 100`}
              />
              <circle
                cx={markerX}
                cy={markerY}
                r="6"
                fill={muted ? "#a3a3a3" : "#d5ffed"}
                stroke="#171717"
                strokeWidth="2"
              />
            </svg>
            <div className="absolute inset-x-0 bottom-5 text-center">
              <p className="text-[11px] text-neutral-500">{t(primary.label)}</p>
              <p className="font-brand text-4xl font-semibold tracking-tight tabular-nums">
                {metricText(primary)}
                <span className="ml-1 text-base font-normal text-neutral-400">
                  {primary.unit}
                </span>
              </p>
            </div>
            {primary.min !== undefined && primary.max !== undefined && (
              <div
                className="-mt-3 flex justify-between px-2 text-[10px] text-neutral-600"
                aria-hidden="true"
              >
                <span>
                  {min}
                  {primary.unit}
                </span>
                <span>
                  {max}
                  {primary.unit}
                </span>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-1">
            {curtain ? (
              <svg
                viewBox="0 0 160 54"
                className="h-12 w-full max-w-40"
                aria-hidden="true"
              >
                <rect
                  x="2"
                  y="2"
                  width="156"
                  height="48"
                  rx="4"
                  fill="#0a0a0a"
                  stroke="#404040"
                />
                <path d="M80 3v46" stroke="#303030" />
                <rect
                  x="4"
                  y="4"
                  width={74 * (1 - fraction)}
                  height="44"
                  rx="2"
                  fill={muted ? "#525252" : "#00884d"}
                />
                <rect
                  x={156 - 74 * (1 - fraction)}
                  y="4"
                  width={74 * (1 - fraction)}
                  height="44"
                  rx="2"
                  fill={muted ? "#525252" : "#00884d"}
                />
              </svg>
            ) : null}
            <div>
              <p className="flex items-center gap-1.5 text-[11px] text-neutral-500">
                {!curtain && <Icon size={18} className={primary.severity === "danger" ? "text-red-400" : primary.severity === "warning" ? "text-orange-400" : "text-accent-muted"} aria-hidden="true" />}
                {t(primary.label)}
              </p>
              <p className={`font-brand ${primary.number === null ? "text-2xl sm:text-3xl" : "text-4xl"} font-semibold leading-tight tracking-tight tabular-nums ${primary.severity === "danger" ? "text-red-400" : primary.severity === "warning" ? "text-orange-400" : ""}`}>
                {metricText(primary)}
                <span className="ml-1 text-base font-normal text-neutral-400">
                  {primary.unit}
                </span>
              </p>
            </div>
          </div>
        )}
      </div>}
      {!!secondary.length && (
        <dl className={primary ? "min-w-16 shrink-0 space-y-2 border-l border-neutral-800 pl-3" : "flex flex-wrap gap-x-4 gap-y-1"}>
          {secondary.map((metric) => (
            <div key={metric.code}>
              <dt className="text-[11px] text-neutral-500">{t(metric.label)}</dt>
              <dd className={`flex items-center gap-1 text-lg font-medium leading-tight tabular-nums ${metric.severity === "danger" ? "text-red-400" : metric.severity === "warning" ? "text-orange-400" : ""}`}>
                {metric.severity && <Warning size={16} aria-hidden="true" />}
                {metricText(metric)}
                <span className="ml-0.5 text-xs text-neutral-500">
                  {metric.unit}
                </span>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
