import { FlowArrow } from "@phosphor-icons/react/FlowArrow";
import { registerModule, type PanelModuleProps } from "../registry";

function LogicModule(_props: PanelModuleProps) {
  return null;
}

registerModule({
  id: "logic",
  label: "Logic",
  icon: FlowArrow,
  order: 20,
  component: LogicModule,
});
