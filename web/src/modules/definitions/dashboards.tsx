import { SquaresFour } from "@phosphor-icons/react/SquaresFour";
import { registerModule, type PanelModuleProps } from "../registry";

function DashboardsModule(_props: PanelModuleProps) {
  return null;
}

registerModule({
  id: "dashboards",
  label: "Dashboards",
  icon: SquaresFour,
  order: 10,
  component: DashboardsModule,
});
