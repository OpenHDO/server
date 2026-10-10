import catalog from "../../../python/openhdo_server/device_types.json";
import type { Device } from "./device-model";

export const deviceTypes = catalog;
const legacyTypes: Record<string, string> = {
  dj: "light", xdd: "light.ceiling", fwd: "light", dc: "light.strip", dd: "light", gyd: "light", fsd: "light",
  cz: "socket", pc: "socket", kg: "switch", wk: "thermostat", fs: "ventilation.fan", jsq: "humidifier",
  wsdcg: "sensor.climate", humidity: "sensor.climate", pir: "sensor.motion", mcs: "sensor.open", ywbj: "sensor.smoke",
  rqbj: "sensor.gas", sj: "sensor.water_leak", cl: "openable.curtain", clkg: "openable.curtain", sd: "vacuum_cleaner",
  sp: "camera", speaker: "media_device", device: "other",
};
export function deviceType(device: Device) {
  if (device.icon === "garland") return "light.garland";
  if (device.kind_override) return legacyTypes[device.kind_override];
  return device.device_type ?? legacyTypes[device.kind] ?? (device.kind in catalog ? device.kind : "other");
}
export function deviceImage(device: Device) {
  const type = deviceType(device) as keyof typeof catalog;
  const entry = catalog[type] ?? catalog.other;
  const power = device.controls.find(control => control.type === "Boolean" && control.code.startsWith("switch"));
  const off = !device.available || !device.enabled || (power && device.state[power.code] === false);
  return `/admin/devices/yandex/${off ? entry.off : entry.on}`;
}
