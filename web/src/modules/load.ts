import { getPanelModules, subscribeToModules } from "./registry";

// ponytail: static build-time discovery; runtime remote modules need signed assets and a server manifest.
const moduleDefinitions = import.meta.glob("./definitions/*.{ts,tsx}", { eager: true });
void moduleDefinitions;

export { getPanelModules, subscribeToModules };
