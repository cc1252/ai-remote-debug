# ARD tool map

Use MCP when the ARD MCP Server is configured. Use the CLI equivalents when MCP is unavailable. Device selectors may be an exact device ID, an exact unique name, or an unambiguous prefix; discover first rather than relying on fuzzy selection.

## Discovery and read-focused diagnostics

| Purpose | MCP tool | CLI equivalent |
|---|---|---|
| List nodes and online state | `list_devices` | `ard devices` |
| Android device details | `get_device_info` | `ard device <device> info` |
| Focused Android logs | `dump_logcat` | `ard logcat <device> --lines <n>` |
| Installed Android packages | `list_apps` | `ard app-list <device>` |
| Android service/app state | `dumpsys_app` | `ard dumpsys <device> <package>` |
| ADB TCP status | `adb_tcp_status` | `ard adb-tcp <device> status` |
| PC agent and SDK tool check | `host_which` | `ard host-which <host>` |

Screen capture and file pull read from the remote device but write customer data locally. Use `screencap` / `ard screencap`, or `file_pull` / `ard pull`, only with a specific destination and retain the result only as needed.

## State-changing or command-dependent tools

| Purpose | MCP tool | CLI equivalent | Boundary |
|---|---|---|---|
| Android shell | `run_shell` | `ard shell ... --confirm` | Arbitrary command; inspect the exact command |
| PC command | `host_exec` | `ard host-exec ... --confirm` | Arbitrary command on the customer PC |
| Start/stop app | `start_app`, `stop_app` | `ard app-start`, `ard app-stop` | Changes application runtime state |
| Clear app data | `clear_app_data` | `ard app-clear ... --confirm` | Deletes the app's local data |
| Send input | `input_keyevent` | `ard input-key` | Controls the visible Android UI |
| Push a file | `file_push` | `ard push ... --confirm` | May overwrite a remote path |
| Install an APK | `install_apk` | `ard install ... --confirm` | Modifies installed software |
| ADB through customer PC | `host_adb` | `ard host-adb` | Risk depends on arguments |
| Fastboot through customer PC | `host_fastboot` | `ard host-fastboot` | Flash/erase/unlock can brick or wipe a device |

Read-only ADB/Fastboot examples include `devices`, `get-state`, `getvar`, and property queries. Treat `reboot`, `install`, `push`, `remount`, `disable-verity`, `flash`, `erase`, `format`, `set_active`, `flashing unlock`, and similar arguments as mutations. `flash`, `erase`, `format`, unlocking, and resets require exact operation-specific approval, not a general request to “take a look.”

## CLI environment

The CLI reads:

- `ARD_RELAY_URL`: Relay HTTP(S) base URL.
- `ARD_API_TOKEN`: Relay bearer token.

Invoke it as `python <repo>/claude-tools/ard.py <command>`. Run `python <repo>/claude-tools/ard.py --help` for the version installed with the repository; prefer that output if it differs from this reference.
