# Connect Tuya / Smart Life

1. Pair your devices in the Tuya Smart or Smart Life mobile app.
2. In that app open **Me → Settings → Account and Security → User Code**.
3. Open HDO **Devices → Add integration → Tuya** and enter the User Code.
4. Scan the QR code with the scanner inside the same mobile app and confirm sign-in.
   HDO checks confirmation automatically; **I've confirmed** retries immediately.

No developer project, Access ID, Access Secret, password or manual region choice is
required in the panel. HDO talks directly to Tuya using the official
[Device Sharing SDK](https://github.com/tuya/tuya-device-sharing-sdk) and the public
application identity published by
[Tuya's Smart Life integration](https://github.com/tuya/tuya-smart-life/blob/main/custom_components/smartlife/const.py).
No Home Assistant installation or connection is involved. Tuya's authorization
screen may label that shared application identity as Home Assistant; HDO does not
have its own registered Tuya application identity. Vendor availability and supported
app accounts depend on Tuya's sharing service.

QR attempts last at most 5 minutes, are held only in server memory and belong to the
admin who starts them. Closing the dialog cancels the attempt; restarting the server
requires a new QR. User Code, endpoint, terminal and access/refresh tokens are stored
privately in the integration database after successful authorization. Tokens refresh
and persist automatically, including when a later inventory read fails. No passwords
are collected. Revoked authorization requires sign-in again from integration settings.
Reconnect must use the same account; it preserves integration/device IDs, names and
rooms. To switch accounts, add a separate integration. Duplicate accounts are rejected.

The older developer-key API remains available for existing integrations; those
connections keep syncing until reauthorized through the account flow. QR sign-in
validates inventory before replacing their credentials. Failed reads retain previous
devices, and rejected commands never count as accepted. Tuya API responses are
sanitized so credentials do not appear in notifications or SDK diagnostics.

Commands respect actual min/max/step/scale and Enum ranges. Json `colour_data` /
`colour_data_v2` uses supplied HSV ranges, or the documented standard ranges for
category `dj` when Tuya returns empty definitions. See the
[standard instruction set](https://developer.tuya.com/en/docs/iot/dj?id=K9i5ql3v98hn3).
Unknown JSON, RAW and
arbitrary String formats remain read-only. Wi-Fi onboarding stays in the Tuya app.
Cloud acceptance does not confirm hardware state; HDO reads state again and syncs.
Inventory and state sync automatically every 30 seconds; the panel refreshes every
10 seconds. Account connections read function definitions during synchronization, including RGB support.
Older developer-key connections cache definitions for up to 10 minutes.
Lamp cards expose power, brightness and color presets with a color wheel. Socket,
switch, fan, thermostat, curtain, vacuum and sensor categories have compact cards;
additional advertised controls are in device settings.

**Devices → Rooms** creates rooms and groups devices across integrations. Choose
devices in room settings, or select a room in individual device settings. Each
device belongs to at most one room; selecting it elsewhere moves it. Room IDs and
assignments survive sync and restart. Rename keeps the ID; deleting a room moves
its devices to Unassigned without deleting them. Room management requires admin
access. Existing local `area` values migrate to rooms on startup.
Cards prioritize the device's main measurement: temperature with a semicircular
scale, curtain position, fan speed, power consumption or a sensor's detection state.
Secondary measurements stay smaller; full readings are available in settings.
Reported-value units and scales come from the device specification API, separately
from writable functions. Developer-key connections can fall back to the function API;
readings without metadata are shown without guessing their decimal scale.

## Linker migration

Stop `openhdo-linker` / `linkerct`. The server no longer loads
`data/modules/connector/linkers.json` or serves Linker/discovery/pairing routes.
Add Tuya in Devices and rebind dashboards/automations to imported device IDs.
Old registries stay untouched for recovery; they are not converted into credentials.
The `linker` and `server-linker` repositories are retired from the active workspace,
with Git history preserved in a sibling archive.
