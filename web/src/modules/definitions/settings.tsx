import { GearSix } from "@phosphor-icons/react/GearSix";
import { registerModule, type PanelModuleProps } from "../registry";

function SettingsModule(_props: PanelModuleProps) {
  return null;
}

registerModule({
  id: "settings",
  label: "Settings",
  icon: GearSix,
  order: 40,
  component: SettingsModule,
});
