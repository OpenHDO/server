import { useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { getPreferences, setPreferences, subscribeToPreferences } from "../i18n";
import { languages, type Language, type Theme } from "../preferences";

export default function SettingsView() {
  const { t } = useTranslation();
  const preferences = useSyncExternalStore(subscribeToPreferences, getPreferences);
  const select = "h-10 w-36 max-w-[50%] rounded-md border border-neutral-700 bg-neutral-950 px-3 text-sm text-neutral-100 outline-none focus:border-accent focus-visible:ring-2 focus-visible:ring-accent";
  return (
    <section className="w-full max-w-4xl space-y-3">
      <h1 className="font-brand text-xl font-bold tracking-tight sm:text-2xl">{t("Settings")}</h1>
      <div className="divide-y divide-neutral-800 rounded-lg bg-neutral-900/50 px-3 sm:px-4">
        <label className="flex items-center justify-between gap-3 py-3 text-sm">
          {t("Language")}
          <select className={select} value={preferences.language} onChange={(event) => setPreferences({ language: event.target.value as Language })}>
            {Object.entries(languages).map(([code, name]) => <option key={code} value={code} lang={code}>{name}</option>)}
          </select>
        </label>
        <label className="flex items-center justify-between gap-3 py-3 text-sm">
          {t("Theme")}
          <select className={select} value={preferences.theme} onChange={(event) => setPreferences({ theme: event.target.value as Theme })}>
            <option value="dark">{t("Dark")}</option>
            <option value="light">{t("Light")}</option>
          </select>
        </label>
      </div>
    </section>
  );
}
