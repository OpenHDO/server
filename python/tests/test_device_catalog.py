"""Catalogue and capability checks independent of the provider packaging."""
import asyncio
import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from openhdo_server.integrations import DeviceSnapshot

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT.parent / 'server-yandex/backend/yandex.py').is_file():
    pytest.skip('Provider mapping tests require the sibling server-yandex plugin checkout', allow_module_level=True)
spec = importlib.util.spec_from_file_location('catalog_yandex', ROOT.parent / 'server-yandex/backend/yandex.py')
yandex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(yandex)


def test_catalog_roundtrips_every_type_and_asset():
    catalog = json.loads((ROOT / 'python/openhdo_server/device_types.json').read_text(encoding='utf-8'))
    assert catalog == yandex.DEVICE_TYPES
    assert len(catalog) == 54
    for kind, entry in catalog.items():
        device = DeviceSnapshot.model_validate(yandex.snapshot({'id': kind, 'name': kind, 'type': 'devices.types.' + kind}))
        assert device.device_type == kind
        for state in ('on', 'off'):
            assert (ROOT / 'web/public/devices/yandex' / entry[state]).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_default_brightness_and_relative_volume():
    device = yandex.snapshot({'id': 'tv', 'name': 'TV', 'type': 'devices.types.media_device.tv', 'capabilities': [
        {'type': 'devices.capabilities.range', 'parameters': {'instance': 'brightness'}},
        {'type': 'devices.capabilities.range', 'parameters': {'instance': 'volume', 'random_access': False}},
    ]})
    assert device['controls'][0]['constraints']['max'] == 100
    relative = device['controls'][1]
    account = yandex.YandexAccount(None, {})
    account.api = AsyncMock(return_value={'devices': [{'id': 'tv', 'capabilities': [{
        'type': 'devices.capabilities.range', 'state': {'instance': 'volume', 'action_result': {'status': 'DONE'}}
    }]}]})
    assert asyncio.run(account.command({}, None, 'tv', relative, -1)) == {}
    action = account.api.call_args.kwargs['json']['devices'][0]['actions'][0]['state']
    assert action == {'instance': 'volume', 'value': -1, 'relative': True}


@pytest.mark.parametrize('url', ['https://camera.example/live.m3u8', 'javascript:alert(1)', 'https://[invalid', 42])
def test_camera_command_validates_stream(url):
    device = yandex.snapshot({'id': 'camera', 'name': 'Camera', 'type': 'devices.types.camera', 'capabilities': [
        {'type': 'devices.capabilities.video_stream', 'parameters': {'protocols': ['hls']}, 'retrievable': False}
    ]})
    account = yandex.YandexAccount(None, {})
    account.api = AsyncMock(return_value={'devices': [{'id': 'camera', 'capabilities': [{
        'type': 'devices.capabilities.video_stream', 'state': {'instance': 'get_stream', 'action_result': {'status': 'DONE'},
        'value': {'protocol': 'hls', 'stream_url': url}}
    }]}]})
    command = account.command({}, None, 'camera', device['controls'][0], 'hls')
    if url == 'https://camera.example/live.m3u8':
        assert asyncio.run(command) == {'video_stream': url}
    else:
        with pytest.raises(yandex.ServiceError):
            asyncio.run(command)
    state = account.api.call_args.kwargs['json']['devices'][0]['actions'][0]['state']
    assert state['value'] == {'protocols': ['hls']}
