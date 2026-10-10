"""Regenerate offline Yandex previews through the production normalizer."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT.parent / "server-yandex/backend"))
from yandex import snapshot
DEVICE_TYPES = json.loads((ROOT / "python/openhdo_server/device_types.json").read_text(encoding='utf-8'))
from openhdo_server.integrations import DeviceSnapshot

MODES = {'cleanup_mode', 'coffee_mode', 'dishwashing', 'fan_speed', 'heat', 'input_source', 'program', 'swing', 'tea_mode', 'thermostat', 'ventilation_mode', 'work_speed'}
TOGGLES = {'backlight', 'controls_locked', 'ionization', 'keep_warm', 'mute', 'oscillation', 'pause'}
RANGES = {'brightness', 'channel', 'humidity', 'open', 'temperature', 'volume', 'fan_speed'}
FLOATS = {'amperage', 'battery_level', 'co2_level', 'electricity_meter', 'food_level', 'gas_meter', 'heat_meter', 'humidity', 'illumination', 'meter', 'pm1_density', 'pm2.5_density', 'pm10_density', 'power', 'pressure', 'temperature', 'tvoc', 'voltage', 'water_level', 'water_meter'}
EVENTS = {'vibration', 'open', 'button', 'motion', 'smoke', 'gas', 'battery_level', 'food_level', 'water_level', 'water_leak'}
UNITS = {'temperature': 'unit.temperature.celsius', 'amperage': 'unit.ampere', 'voltage': 'unit.volt', 'power': 'unit.watt', 'humidity': 'unit.percent', 'battery_level': 'unit.percent', 'food_level': 'unit.percent', 'water_level': 'unit.percent', 'co2_level': 'unit.ppm', 'illumination': 'unit.illumination.lux', 'electricity_meter': 'unit.kilowatt_hour', 'gas_meter': 'unit.cubic_meter', 'water_meter': 'unit.cubic_meter', 'heat_meter': 'unit.gigacalorie', 'pressure': 'unit.pressure.pascal', 'tvoc': 'unit.ppm', 'pm1_density': 'unit.density.mcg_m3', 'pm2.5_density': 'unit.density.mcg_m3', 'pm10_density': 'unit.density.mcg_m3'}


def previews():
    fixtures = []
    for kind, entry in DEVICE_TYPES.items():
        raw = {'id': 'yandex-' + kind, 'name': entry['name'], 'type': 'devices.types.' + kind, 'state': 'online', 'capabilities': [], 'properties': []}
        for family, values in entry['recommended'].items():
            short = family.split('.')[-1]
            def capability(parameters, instance, value):
                raw['capabilities'].append({'type': family, 'parameters': parameters, 'state': {'instance': instance, 'value': value}})
            if short == 'on_off':
                capability({}, 'on', True)
            elif short == 'color_setting':
                capability({'color_model': 'hsv', 'temperature_k': {'min': 2700, 'max': 6500}}, 'hsv', {'h': 210, 's': 70, 'v': 65})
            elif short == 'video_stream':
                raw['capabilities'].append({'type': family, 'retrievable': False, 'parameters': {'protocols': ['hls']}})
            elif short == 'range':
                for instance in dict.fromkeys(value for value in values if value in RANGES):
                    low, high, unit = (16, 30, 'unit.temperature.celsius') if instance == 'temperature' else (0, 100, 'unit.percent')
                    if instance == 'channel':
                        low, high, unit = 1, 100, ''
                    if kind.startswith('cooking') and instance == 'temperature':
                        low, high = 40, 100
                    if kind.startswith('media_device') and instance == 'volume':
                        parameters, value = {'instance': instance, 'random_access': False, 'range': {'precision': 1}}, None
                    else:
                        parameters, value = {'instance': instance, 'range': {'min': low, 'max': high, 'precision': 1}, 'unit': unit}, round((low + high) / 2)
                    capability(parameters, instance, value)
            elif short == 'mode':
                for index, instance in enumerate(values):
                    if instance not in MODES:
                        continue
                    options = []
                    for option in values[index + 1:]:
                        if option in MODES:
                            break
                        if not option.startswith('unit.'):
                            options.extend(part.strip() for part in option.split(',') if part.strip())
                    options = list(dict.fromkeys(options)) or ['auto', 'low', 'high']
                    capability({'instance': instance, 'modes': [{'value': value} for value in options]}, instance, options[0])
            elif short == 'toggle':
                for instance in dict.fromkeys(value for value in values if value in TOGGLES):
                    capability({'instance': instance}, instance, False)
            elif short in {'float', 'event'}:
                for instance in dict.fromkeys(value for value in values if value in (FLOATS if short == 'float' else EVENTS)):
                    value = {'temperature': 23.5, 'humidity': 45, 'battery_level': 87, 'power': 125, 'voltage': 230, 'amperage': 0.54, 'illumination': 420, 'pressure': 101325, 'co2_level': 650, 'electricity_meter': 1234.5, 'gas_meter': 54.2, 'water_meter': 23.6}.get(instance, 60)
                    if short == 'event':
                        value = {'motion': 'not_detected', 'open': 'closed', 'button': 'click', 'vibration': 'tilt', 'smoke': 'not_detected', 'gas': 'not_detected', 'water_leak': 'dry'}.get(instance, 'normal')
                    raw['properties'].append({'type': family, 'parameters': {'instance': instance, **({'unit': UNITS.get(instance, '')} if short == 'float' else {})}, 'state': {'instance': instance, 'value': value}})
        view = DeviceSnapshot.model_validate(snapshot(raw)).model_dump()
        view.update(id='preview-' + raw['id'], integration_id='design-preview', area='', room_id=None, enabled=True, kind_override=None)
        fixtures.append({'group': entry['group'], 'previewState': 'on', 'device': view})
    return fixtures


if __name__ == '__main__':
    fixtures = previews()
    (ROOT / 'web/src/design-preview/yandex-fixtures.json').write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Generated {len(fixtures)} Yandex device types")
