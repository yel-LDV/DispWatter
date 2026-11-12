# Developer Mode

Access advanced operations on the ESP32 using button combinations.

## Buttons Layout

The ESP32 uses 6 physical buttons connected to GND (active LOW with INPUT_PULLUP):

| Button | GPIO | Function |
|--------|------|----------|
| Up | GPIO 15 | Navigate up / mode switch combo |
| Down | GPIO 2 | Navigate down / mode switch combo |
| Left | GPIO 21 | Page back / return to normal mode |
| Right | GPIO 16 | Page forward |
| OK (center) | GPIO 0 | Confirm selection / long press for mode switch |
| Power | GPIO 32 | Wake from deep sleep |

## Mode Switches

Hold button combinations for 2 seconds to switch modes:

| Combination | Mode | LCD Display |
|-------------|------|-------------|
| OK + Up (2s) | OTA | "Modo: OTA / Espera backend" |
| OK + Down (2s) | Downgrade | "Modo: Downgrade / Espera backend" |
| OK + Up + Right (2s) | Developer | "Modo: Dev / OK+Up+Right" |
| OK + Left | Normal | Returns to normal telemetry display |

## Developer Mode Menu

Once in developer mode, navigate with Left/Right buttons and confirm with OK:

| Option | Action |
|--------|--------|
| 1/4 Reiniciar | Reboots the ESP32 |
| 1/4 Desvincular | Factory reset: clears key_hash, resets to PENDING_CLAIM |
| 1/4 Info firmware | Shows flash usage (sketch size / free space) |
| 1/4 Info red | Shows current WiFi SSID and IP address |

### Navigation

- **Left/Right**: Move between menu options
- **OK**: Execute selected option
- **OK + Left**: Exit developer mode and return to normal display

## Pin Assignment Notes

- GPIO 4 is reserved for the relay (PIN_RELE). Do NOT assign buttons to this pin.
- GPIO 21 was chosen for the Left button to avoid conflict with the relay.
- GPIO 32 is used for the Power button (wake from deep sleep).
