import { PlugsConnected } from "@phosphor-icons/react/PlugsConnected";
import { registerModule, type PanelModuleProps } from "../registry";

function ConnectorModule(_props: PanelModuleProps) {
  return null;
}

registerModule({
  id: "connector",
  label: "Connector",
  icon: PlugsConnected,
  order: 30,
  component: ConnectorModule,
});
