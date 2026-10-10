export const languages: Record<string, string> = { en: "English", fr: "Français", es: "Español", zh: "中文", ru: "Русский" };
export type Language = keyof typeof languages;
export type Theme = string;
export const themeNames: Record<string, string> = { dark: "Dark", light: "Light" };
export type Preferences = { language: Language; theme: Theme };
export const preferenceKey = "openhdo.preferences";
export const defaults: Preferences = { language: "en", theme: "dark" };

export function parsePreferences(value: string | null): Preferences {
  try {
    const parsed = JSON.parse(value ?? "null");
    return {
      language: typeof parsed?.language === "string" && /^[a-z]{2,3}(?:-[A-Za-z0-9]+)*$/.test(parsed.language) ? parsed.language : defaults.language,
      theme: typeof parsed?.theme === "string" && /^[a-z0-9][a-z0-9:.-]*$/.test(parsed.theme) ? parsed.theme : defaults.theme,
    };
  } catch {
    return { ...defaults };
  }
}

export function readPreferences(storage: Pick<Storage, "getItem">): Preferences {
  try { return parsePreferences(storage.getItem(preferenceKey)); }
  catch { return { ...defaults }; }
}

export function writePreferences(storage: Pick<Storage, "setItem">, preferences: Preferences) {
  // Privacy modes can deny storage; settings still work for the current session.
  try { storage.setItem(preferenceKey, JSON.stringify(preferences)); } catch { /* storage unavailable */ }
}
