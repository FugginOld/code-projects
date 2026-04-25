# ADS-B Pi TUI

`adsb_tui.py` is a no-dependency curses dashboard for a Raspberry Pi ADS-B receiver.

It focuses on three groups of metrics:

- Pi: CPU, load, temperature, memory, disk, uptime, network throughput
- SDR: Airspy gain, sample rate, decode rate, RSSI/SNR/noise, lost buffers
- ADS-B: aircraft counts, message rate, position rate, CPR success, feed traffic, live range
- Autotune: current autotune status, last command output, and a mini command field

## Layout

On a normal Pi terminal width, the screen is split into:

- upper-left 25%: Pi performance
- lower-left 25%: Airspy Mini SDR performance
- upper-right: ADS-B performance
- lower-right: autotune command panel

On smaller terminals, it falls back to stacked panels.

## Expected JSON paths

The dashboard checks these paths in order:

- `/run/adsb-feeder-airspy/airspy_adsb/stats.json`
- `/run/airspy_adsb/stats.json`
- `/run/adsb-feeder-ultrafeeder/readsb/stats.json`
- `/run/adsb-feeder-ultrafeeder/readsb/status.json`
- `/run/adsb-feeder-ultrafeeder/readsb/receiver.json`
- `/run/adsb-feeder-ultrafeeder/readsb/aircraft.json`
- `/run/readsb/stats.json`
- `/run/readsb/status.json`
- `/run/readsb/receiver.json`
- `/run/readsb/aircraft.json`

## Run

```bash
python3 adsb_tui.py
```

Press `q` to quit.
Press `:` to open the autotune mini command field.
Press `?` to open the built-in help overlay.
For any `live` command, press `y` to confirm or `n`/`Esc` to cancel.

## Autotune Panel

The TUI looks for:

- `./autotune.py`
- `./config.json`

When present, the lower-right panel can run the autotune helper without leaving the dashboard.
The panel also shows a one-line safe-start reminder, and `?` opens a full on-screen operator guide.

## Safe Sequence

If you just want the safest operator flow, follow this exact order:

1. Start the TUI and confirm all four panels are updating normally.
2. Press `:` and run `baseline`.
3. Press `:` and run `score`.
4. Press `:` and run `plan`.
5. Press `:` and run `loop`.
6. Read the panel output and make sure the dry-run plan looks reasonable.
7. If you want a live gain test, run `loop live`.
8. Only after gain testing looks stable, try `plan timeout` and `loop timeout`.
9. Only after timeout testing looks stable, try `plan cputime_target` and `loop cputime_target`.

Recommended first-day sequence:

- `baseline`
- `score`
- `plan`
- `loop`

Recommended first live sequence:

- `loop live`
- wait for the candidate cycle to finish
- read the final reported best value
- if the result looks wrong, use `rollback live`

Safety behavior:

- `apply`, `gain`, `loop`, and `rollback` default to dry-run
- add `live` at the end to allow an actual Expert-page write
- every `live` command asks for confirmation before it runs
- the panel keeps the last command output visible after completion
- dry-run means the command shows what it would do without changing the feeder

## Mini Command Guide

These commands are entered after pressing `:`.

- `baseline`
  - Captures the current station state and writes a baseline snapshot.
  - Use this first before any tuning work.
- `score`
  - Scores the current station state using the autotune scoring rules.
  - Use this after `baseline` so you know where you started.
- `plan`
  - Creates a dry-run gain sweep plan using the configured gain candidates.
  - Use this before `loop` so you can see what values will be tried.
- `plan timeout`
  - Creates a dry-run plan for the named variable instead of gain.
  - Good next step after gain is stable.
- `plan cputime_target`
  - Creates a dry-run plan for CPU target values.
- `render KEY=VALUE ...`
  - Builds the full Expert-page environment block without posting it.
  - Use this to inspect exactly what would be sent.
- `apply KEY=VALUE ...`
  - Dry-run preview of a manual environment change.
  - Example: `apply AIRSPY_ADSB_TIMEOUT=75`
- `apply KEY=VALUE ... live`
  - Actually posts the full environment block to the ADS-B image Expert page and waits for restart.
  - Use this only if you want to force a specific manual setting.
  - The TUI will ask for confirmation before it runs.
- `gain VALUE`
  - Dry-run preview of setting `AIRSPY_ADSB_GAIN`.
  - Example: `gain 18`
- `gain VALUE live`
  - Actually applies the chosen gain and restarts the feeder stack.
  - The TUI will ask for confirmation before it runs.
- `loop`
  - Dry-run automated gain loop.
  - This is the safest way to verify candidate order, warmup timing, and observation timing.
- `loop live`
  - Live automated gain loop.
  - The tool applies each gain candidate, waits through warmup, samples over the observation window, and keeps only accepted improvements.
  - The TUI will ask for confirmation before it runs.
- `loop timeout`
  - Dry-run automated loop for the `timeout` variable definition.
- `loop timeout live`
  - Live automated loop for the `timeout` variable definition.
- `loop cputime_target`
  - Dry-run automated loop for CPU target values.
- `loop cputime_target live`
  - Live automated loop for CPU target values.
- `rollback`
  - Dry-run preview of the last saved rollback state.
- `rollback live`
  - Actually restores the previous environment block and restarts the feeder stack.
  - The TUI will ask for confirmation before it runs.

## What To Expect

When you run a live tuning command:

1. The TUI will show the command as running.
2. The ADS-B image Expert page settings will be updated.
3. The feeder stack will restart.
4. The autotune logic will wait through the configured warmup period.
5. It will then collect repeated samples for the configured observation window.
6. It will compare the new averaged result against the current best result.
7. It will either keep the new value or roll back to the previous best value.

This means a live loop can take a while. That is normal.

## Dummy-Proof Rules

If you are unsure, follow these rules:

- Do not start with `live`.
- If you do use `live`, read the confirmation prompt before pressing `y`.
- Always run `baseline` before the first tuning session.
- Always run `score` before the first tuning session.
- Always run `plan` or `loop` in dry-run before `loop live`.
- Change one variable family at a time.
- Start with gain.
- Use `timeout` only after gain looks stable.
- Use `cputime_target` only after timeout looks stable.
- If a live result feels wrong, use `rollback live`.
- If the station is already working well, stop after a clearly better result and do not keep chasing tiny gains.

## Install On The Pi

Your Pi details:

- host: `192.168.9.74`
- user: `pi`
- target folder: `/home/pi/adsb-tui`

curl -fsSL https://raw.githubusercontent.com/FugginOld/code-projects/main/adsb-tui-claude/install.sh

On the Pi, install the launcher:

```bash
cd /home/pi/adsb-tui
chmod +x install.sh
./install.sh
```

If `~/.local/bin` is not in your shell path yet, enable it for the current shell:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Start the dashboard manually:

```bash
adsb-tui
```

Press `q` to quit.

## Optional Boot Service

If you want the dashboard to start automatically on the Pi console, run these exact commands on the Pi:

```bash
cd /home/pi/adsb-tui
sudo cp adsb-tui.service /etc/systemd/system/adsb-tui.service
sudo systemctl daemon-reload
sudo systemctl enable adsb-tui.service
sudo systemctl start adsb-tui.service
```

Check status with:

```bash
sudo systemctl status adsb-tui.service
```

Notes:

- the service is set to run on `/dev/tty1`
- it is configured for user `pi`
- it uses `/home/pi/adsb-tui/adsb_tui.py`

Useful service commands:

```bash
sudo systemctl restart adsb-tui.service
sudo systemctl stop adsb-tui.service
sudo systemctl disable adsb-tui.service
journalctl -u adsb-tui.service -n 50 --no-pager
```
