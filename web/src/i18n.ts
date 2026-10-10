import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import fr from "./locales/fr.json";
import es from "./locales/es.json";
import zh from "./locales/zh.json";
import ru from "./locales/ru.json";
import { languages, themeNames, defaults, parsePreferences, preferenceKey, readPreferences, writePreferences, type Preferences } from "./preferences";

let preferences = { ...defaults };
try { preferences = readPreferences(window.localStorage); } catch { /* storage unavailable */ }
const listeners = new Set<() => void>();
export const getPreferences = () => preferences;
export const subscribeToPreferences = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};

void i18next.use(initReactI18next).init({
  resources: { en: { translation: en }, fr: { translation: fr }, es: { translation: es }, zh: { translation: zh }, ru: { translation: ru } },
  lng: preferences.language,
  fallbackLng: "en",
  keySeparator: false,
  nsSeparator: false,
  initAsync: false,
  interpolation: { escapeValue: false },
});

export const t = (key: string, values?: Record<string, string | number>) => i18next.t(key, values);
export const formatNumber = (value: number, maximumFractionDigits = 2) =>
  new Intl.NumberFormat(preferences.language, { maximumFractionDigits }).format(value);
export const formatDate = (date: Date) =>
  new Intl.DateTimeFormat(preferences.language, { dateStyle: "medium", timeStyle: "short" }).format(date);

function applyPreferences() {
  const theme = pluginThemes.get(preferences.theme);
  document.documentElement.dataset.theme = theme?.base ?? preferences.theme;
  for (const key of appliedThemeKeys) document.documentElement.style.removeProperty(key);
  appliedThemeKeys.clear();
  for (const [key, value] of Object.entries(theme?.variables ?? {})) { document.documentElement.style.setProperty(key, value); appliedThemeKeys.add(key); }
  document.documentElement.lang = preferences.language === "zh" ? "zh-Hans" : preferences.language;
  document.documentElement.style.colorScheme = theme?.base ?? preferences.theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", preferences.theme === "dark" ? "#0a0a0a" : "#fafafa");
  void i18next.changeLanguage(preferences.language);
  document.title = t("OpenHDO panel");
}

export function setPreferences(change: Partial<Preferences>) {
  preferences = parsePreferences(JSON.stringify({ ...preferences, ...change }));
  try { writePreferences(window.localStorage, preferences); } catch { /* storage unavailable */ }
  applyPreferences();
  listeners.forEach((listener) => listener());
}
window.addEventListener("storage", (event) => {
  if (event.key !== preferenceKey && event.key !== null) return;
  preferences = parsePreferences(event.newValue);
  applyPreferences();
  listeners.forEach((listener) => listener());
});
const pluginThemes = new Map<string, { base: "dark" | "light"; variables: Record<string, string> }>();
const appliedThemeKeys = new Set<string>();
export function registerTheme(theme: { id: string; name: string; base: "dark" | "light"; variables: Record<string, string> }) {
  if (Object.hasOwn(themeNames, theme.id) || !["dark", "light"].includes(theme.base)) throw new Error("Invalid or conflicting theme");
  for (const [key, value] of Object.entries(theme.variables)) if (!/^--[a-z0-9-]+$/.test(key) || typeof value !== "string" || /[;{}]|url\s*\(/i.test(value)) throw new Error("Invalid theme variable");
  pluginThemes.set(theme.id, theme); themeNames[theme.id] = theme.name;
  preferences = { ...preferences }; applyPreferences();
  listeners.forEach((listener) => listener());
  return () => { pluginThemes.delete(theme.id); delete themeNames[theme.id]; if (preferences.theme === theme.id) setPreferences({ theme: "dark" }); };
}
const languageOwners = new Set<string>();
export function registerLanguage(code: string, name: string, strings: Record<string, string>, replace = false) {
  if (!/^[a-z]{2,3}(?:-[A-Za-z0-9]+)*$/.test(code) || languageOwners.has(code) || (Object.hasOwn(languages, code) && !replace) || Object.values(strings).some((value) => typeof value !== "string")) throw new Error("Invalid or conflicting language");
  const oldName = languages[code];
  const oldStrings = i18next.hasResourceBundle(code, "translation") ? { ...i18next.getResourceBundle(code, "translation") } : null;
  languageOwners.add(code);
  languages[code] = name; i18next.addResourceBundle(code, "translation", { ...oldStrings, ...strings }, true, true);
  preferences = { ...preferences }; applyPreferences();
  listeners.forEach((listener) => listener());
  return () => {
    languageOwners.delete(code); i18next.removeResourceBundle(code, "translation");
    if (oldStrings) i18next.addResourceBundle(code, "translation", oldStrings);
    if (oldName) languages[code] = oldName; else delete languages[code];
    if (!oldName && preferences.language === code) setPreferences({ language: "en" });
    else { preferences = { ...preferences }; applyPreferences(); listeners.forEach((listener) => listener()); }
  };
}
applyPreferences();

const errorKeys: Record<string, string> = {
  invalid_credentials: "Invalid username or password", authorization_required: "Sign in to continue",
  forbidden: "Permission denied", csrf_required: "Session expired. Sign in again.", validation_error: "Check the form fields",
  integration_not_found: "Integration not found", room_not_found: "Room not found", device_not_found: "Device not found",
  room_exists: "A room with this name already exists", integration_exists: "Account already connected",
  device_unavailable: "Device is unavailable or disabled", unsupported_action: "This device does not support the command",
  invalid_value: "Value does not match the device function specification", too_many_logins: "Too many sign-in attempts. Try again later.",
  provider_mismatch: "Provider cannot be changed", login_not_found: "Sign-in attempt not found", login_expired: "Sign-in code expired. Start sign-in again.",
  invalid_inventory: "Invalid device inventory", duplicate_device: "Device selection contains duplicates",
  account_authentication_required: "Reconnect this integration through account sign-in", account_mismatch: "Sign in to the same account to reconnect",
  yandex_not_configured: "Sign-in is not configured", yandex_login_expired: "Session expired. Sign in again.",
  yandex_command_rejected: "Provider did not accept the device command",
  yandex_device_unavailable: "Device is unavailable or disabled",
};
const authErrors: Record<string, string> = {
  "username is already registered": "Username already exists", "user does not exist": "User not found",
  "the last active admin cannot be deleted": "Cannot remove the last admin",
  "the last active admin cannot be disabled or demoted": "Cannot remove the last admin",
  "unsupported user role": "Check the form fields",
};

export async function responseError(response: Response) {
  const payload = await response.json().catch(() => null) as { error?: string; detail?: string } | null;
  const key = payload?.error && errorKeys[payload.error];
  if (key) return t(key);
  if (payload?.detail && authErrors[payload.detail]) return t(authErrors[payload.detail]);
  if (payload?.detail && i18next.exists(payload.detail)) return t(payload.detail);
  if (payload?.error?.startsWith("tuya_") || payload?.error?.includes("yandex")) return t("Unable to connect to provider");
  return t("Request failed ({{status}})", { status: response.status });
}

const enumLabels: Record<string, string> = {
  one: "1", two: "2", three: "3", four: "4", five: "5", six: "6", seven: "7", eight: "8", nine: "9", ten: "10",
  black_tea: "Black tea", flower_tea: "Flower tea", green_tea: "Green tea", herbal_tea: "Herbal tea", oolong_tea: "Oolong", puerh_tea: "Pu-erh", red_tea: "Red tea", white_tea: "White tea",
  espresso: "Espresso", americano: "Americano", cappuccino: "Cappuccino", latte: "Latte", fan_only: "Fan", turbo: "Turbo", quiet: "Quiet", horizontal: "Horizontal", vertical: "Vertical",
  white: "White", colour: "Colour", color: "Colour", scene: "Scene", music: "Music", auto: "Auto", manual: "Manual",
  low: "Low", middle: "Medium", medium: "Medium", high: "High", stop: "Stop", open: "Open", close: "Close", closed: "Closed",
  pause: "Pause", heat: "Heat", cool: "Cool", dry: "Dry", sleep: "Sleep", cleaning: "Cleaning", charging: "Charging",
  standby: "Standby", smart: "Smart", comfort: "Comfort", eco: "Eco", connected: "Connected", connecting: "Connecting", error: "Error",
};
export const enumLabel = (value: string) => t(enumLabels[value] ?? value.replaceAll("_", " "));
export const metricText = (metric: { number: number | null; text: string }) =>
  metric.number === null ? enumLabel(metric.text) : formatNumber(metric.number);
