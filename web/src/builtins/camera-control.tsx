import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { VideoCamera } from "@phosphor-icons/react/VideoCamera";
import { X } from "@phosphor-icons/react/X";
import { useNotifications } from "../notifications";

export default function CameraControl({ value, disabled, send }: {
  value: unknown; disabled: boolean; send: () => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const notify = useNotifications();
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState('');
  useEffect(() => {
    if (typeof value === 'string' && (value === 'demo:camera' || /^https?:\/\//.test(value))) setSource(value);
  }, [value]);
  const dialog = useRef<HTMLDialogElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (!open) return;
    const origin = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => { dialog.current?.close(); origin?.focus(); };
  }, [open]);
  useEffect(() => {
    const player = video.current;
    if (!open || !player || !/^https?:\/\//.test(source)) return;
    let active = true;
    let release: (() => void) | undefined;
    const failed = () => notify('error', t('Unable to play camera stream'));
    if (player.canPlayType('application/vnd.apple.mpegurl')) player.src = source;
    else void import('hls.js').then(({ default: Hls }) => {
      if (!active) return;
      if (!Hls.isSupported()) { failed(); return; }
      const hls = new Hls();
      release = () => hls.destroy();
      hls.on(Hls.Events.ERROR, (_, error) => { if (error.fatal) failed(); });
      hls.loadSource(source);
      hls.attachMedia(player);
    }).catch(failed);
    player.addEventListener('error', failed);
    return () => { active = false; release?.(); player.removeEventListener('error', failed); player.removeAttribute('src'); player.load(); };
  }, [open, source, notify, t]);
  return <>
    <button disabled={disabled} className="flex w-full items-center justify-center gap-2 rounded-lg bg-neutral-800 px-3 py-2 text-sm disabled:opacity-40"
      onClick={async () => { if (await send()) setOpen(true); }}><VideoCamera size={20} />{t('View camera')}</button>
    {open && <dialog ref={dialog} aria-label={t('Camera')} onCancel={() => setOpen(false)}
      className="fixed inset-0 m-auto w-[min(52rem,calc(100vw-2rem))] rounded-xl border border-neutral-800 bg-neutral-950 p-3 text-neutral-100 backdrop:bg-black/70">
      <div className="mb-2 flex items-center justify-between"><span>{t('Camera')}</span><button aria-label={t('Close')} onClick={() => setOpen(false)}><X size={22} /></button></div>
      {source === 'demo:camera' ? <div className="relative aspect-video overflow-hidden rounded-lg bg-neutral-900">
        <svg viewBox="0 0 640 360" className="h-full w-full" aria-label={t('Camera preview')}><path d="M0 240L220 160L640 200V360H0Z" fill="#262626" /><path d="M150 180V85H360V180M255 85V180" stroke="#525252" strokeWidth="8" fill="none" /><rect x="390" y="150" width="140" height="100" rx="8" fill="#404040" /><path d="M0 360L320 220L640 360" stroke="#737373" fill="none" /></svg>
        <span className="absolute left-3 top-3 font-mono text-xs">DEMO · 1920 × 1080</span>
      </div> : <video ref={video} controls autoPlay playsInline className="aspect-video w-full rounded-lg bg-black" />}
    </dialog>}
  </>;
}
