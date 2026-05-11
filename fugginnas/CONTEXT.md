# FugginNAS — Project Context

## Project Overview

A self-hosted browser-based setup and management wizard for building a home NAS on
fresh Debian. The tool configures a proper mergerfs cache-tier pool, parity
protection (SnapRAID scheduled OR NonRAID live), Docker + Compose stack management,
SMB/NFS sharing, and systemd scheduling — all from a guided web UI served locally.

**Project name (working):** `FugginNAS`
**Target OS:** Debian (fresh install, any recent stable release)
**Served on:** localhost, configurable port (default 7070)
**Requires root:** Yes — all config writes and service management need sudo/root

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3 + Flask | Thin server, subprocess management, config file writes |
| Frontend | Vanilla JS + HTML/CSS | No build step; single-page app feel via JS routing |
| Styling | Custom CSS (no framework) | Dark industrial aesthetic — see UI section |
| System comms | `subprocess`, `lsblk`, `systemctl` | All called server-side, output streamed via SSE |
| Config persistence | JSON sidecar (`/etc/FugginNAS/state.json`) | Tracks what was configured and when |
| Packaging | Single repo, `install.sh` bootstrap | Installs deps, creates systemd service for the UI itself |

---

## Architecture

```
FugginNAS/
├── install.sh                  # Bootstrap: apt deps, pip, systemd unit
├── app.py                      # Flask entrypoint
├── routes/
│   ├── drives.py               # /api/drives — lsblk discovery
│   ├── pool.py                 # /api/pool — mergerfs mount/fstab
│   ├── cache.py                # /api/cache — cache tier + mover script
│   ├── snapraid.py             # /api/snapraid — config + systemd timer
│   ├── nonraid.py              # /api/nonraid — array create/start/status/check
│   ├── shares.py               # /api/shares — samba + nfs config
│   └── status.py               # /api/status — live dashboard data
├── system/
│   ├── drive_utils.py          # lsblk parsing, device info
│   ├── fstab.py                # Read/write /etc/fstab safely (backup first)
│   ├── mergerfs.py             # Build mergerfs mount strings
│   ├── snapraid_conf.py        # Generate snapraid.conf
│   ├── nonraid_utils.py        # nmdctl wrappers, array status parsing
│   ├── nonraid_install.py      # PPA add, dkms + tools install, kernel headers
│   ├── systemd.py              # Write/enable/start timers and services
│   ├── samba.py                # Write smb.conf share blocks
│   ├── nfs.py                  # Write /etc/exports entries
│   └── mover.py                # Generate cache mover script
├── templates/
│   └── index.html              # Single HTML shell; JS handles routing
├── static/
│   ├── app.js                  # SPA router + all screen logic
│   ├── style.css               # Design system
│   └── icons/                  # SVG icons
└── state/
    └── state.json              # Persisted config state (runtime)
```

---

## Wizard Screen Flow

```
[ 1. Welcome ]
  - Root check (warn if not root)
  - Dependency check: mergerfs, samba, nfs-kernel-server
  - Install missing deps button (apt)

[ 2. Storage Backend Selection ]  ← NEW SCREEN
  - Choose parity engine:
      ○ NonRAID + MergerFS   — live real-time parity (unRAID-style kernel driver)
      ○ SnapRAID + MergerFS  — scheduled parity, lower write overhead (default)
      ○ MergerFS only        — no parity, pooling only
  - Shows comparison table: live vs scheduled, write perf, recovery model
  - Selection gates which config screens follow (Step 5 varies by choice)

[ 3. Drive Selection ]
  - Table of all block devices from lsblk
  - Tag each: Cache | Data | Parity | Ignore
  - Shows: device, size, model, current mount, filesystem
  - Validation: must have ≥1 data, ≥1 parity (unless MergerFS-only), ≥1 cache
  - NonRAID mode: warns parity drive must be ≥ largest data drive
  - NonRAID mode: warns drives must be pre-partitioned (sgdisk command shown)

[ 4. Pool Configuration ]
  - Pool mount point (default: /mnt/pool)
  - Cache mount point (default: /mnt/cache)
  - Data disks mount points (auto-generated: /mnt/disk1, /mnt/disk2 ...)
  - mergerfs write policy: mfs (most free space) | lfs | existing
  - Cache tier policy: cache drives write first; mover migrates to pool
  - NonRAID mode: pool layered on top of /dev/nmdXp1 devices, not raw disks
  - SnapRAID mode: Parity file path (default: /mnt/parity1/snapraid.parity)

[ 5a. SnapRAID Configuration ]  (shown if SnapRAID backend selected)
  - Parity mode: Single (default) | Dual (adds second parity drive selector)
  - Content file locations (auto-placed on each data disk + one on parity)
  - Sync schedule: daily time picker (default 02:00)
  - Scrub schedule: Weekly | Monthly | Off (default Weekly, 5% of array)
  - Scrub plan: oldest-first

[ 5b. NonRAID Configuration ]  (shown if NonRAID backend selected)
  - Install NonRAID? Yes / No / Already installed (auto-detected)
    → installs nonraid-dkms + nonraid-tools via PPA + kernel headers meta-package
  - Parity mode: Single (default) | Dual
  - Per-disk filesystem: XFS (default) | BTRFS | ZFS | ext4 (per slot)
  - LUKS encryption per disk? Yes / No (keyfile path: /etc/nonraid/luks-keyfile)
  - Turbo write mode: Off (default) | On (md_write_method=1)
  - Parity check schedule: Quarterly (default, matches nonraid timer) | Monthly | Off
  - Shows nmdctl create will be run interactively post-apply (SSE terminal)

[ 6. Cache Mover ]
  - Mover schedule: daily time picker (default 03:00)
  - Mover threshold: move files older than N hours (default 24)
  - Mover min free on cache: trigger if cache >X% full (default 80%)
  - Shows generated mover script preview

[ 7. Share Setup ]
  - Protocol: SMB | NFS | Both
  - Share name (default: pool)
  - Share path (default: pool mount point)
  - SMB options: guest ok | require auth (username/password entry)
  - NFS options: allowed hosts CIDR (default 192.168.0.0/16), ro/rw
  - Can add multiple shares

[ 7. Summary + Apply ]
  - Shows every file that will be written (diff view)
  - Files (SnapRAID path): /etc/fstab additions, /etc/snapraid.conf, systemd timer units,
           /etc/samba/smb.conf additions, /etc/exports additions,
           /usr/local/bin/FugginNAS-mover.sh
  - Files (NonRAID path): nonraid PPA + dkms install, /etc/default/nonraid,
           /nonraid.dat superblock location, nmdctl array create (interactive SSE),
           mergerfs fstab entries on /dev/nmdXp1 mounts,
           /etc/samba/smb.conf additions, /etc/exports additions,
           /usr/local/bin/FugginNAS-mover.sh
  - Single "Apply All" button
  - Streams apply output to terminal pane (SSE)

[ 8. Status Dashboard ]
  - Pool: mount status, used/free per disk, cache fill %
  - Parity panel (adapts to backend):
      SnapRAID: last sync time/result, last scrub, dirty file count
               Actions: Run Sync Now | Run Scrub Now
      NonRAID:  array status (STARTED/DEGRADED/STOPPED), last parity check,
               sync errors, disk slot health
               Actions: Run Parity Check | View nmdctl status
  - Shares: SMB status, NFS status, active connections
  - Actions: Run Mover Now
  - Live log tail for running jobs (SSE)
```

---

## Cache Tier Design

Uses a two-layer mergerfs stack (standard Unraid-style pattern):

```
/mnt/cache          ← fast SSD/NVMe, tagged Cache in wizard
/mnt/disk1..N       ← slow HDDs, tagged Data

Layer 1 (cache pool):  mergerfs /mnt/cache:/mnt/disk* → /mnt/pool
  write policy: mfs or "existing" (writes to cache first if space available,
                falls back to data disks)

Mover script (cron/systemd):
  - Runs nightly (configurable)
  - Finds files on cache older than threshold
  - rsync --remove-source-files cache → matching data disk path
  - Respects min-free threshold on cache before triggering
```

Mover script skeleton:
```bash
#!/bin/bash
# FugginNAS-mover.sh — generated by FugginNAS
CACHE=/mnt/cache
POOL=/mnt/pool
MIN_FREE_PCT=20
AGE_HOURS=24

cache_used_pct=$(df --output=pcent "$CACHE" | tail -1 | tr -d ' %')
if [ "$cache_used_pct" -lt $((100 - MIN_FREE_PCT)) ]; then
  exit 0  # Cache not full enough, skip
fi

find "$CACHE" -mindepth 1 -not -path '*/\.*' \
  -mmin +$((AGE_HOURS * 60)) -type f | while read -r file; do
  rel="${file#$CACHE/}"
  dest="$POOL/$rel"
  mkdir -p "$(dirname "$dest")"
  rsync -ax --remove-source-files "$file" "$dest"
done
```

---

## SnapRAID Configuration Template

```
# Generated by FugginNAS
parity /mnt/parity1/snapraid.parity
# 2-parity (uncomment and add drive to enable):
# 2-parity /mnt/parity2/snapraid.parity

content /var/snapraid/snapraid.content
content /mnt/disk1/snapraid.content
content /mnt/disk2/snapraid.content

data d1 /mnt/disk1
data d2 /mnt/disk2

exclude *.tmp
exclude *.!sync
exclude /tmp/
```


---

## NonRAID Integration

### What NonRAID is

A fork of the unRAID `md_unraid` kernel driver, packaged as a DKMS module for
Debian 12/13 and Ubuntu 24.04. It provides live, real-time parity protection in
the unRAID style — each data disk gets a virtual block device (`/dev/nmdXp1`)
with parity calculated on every write. Works alongside mergerfs exactly like
unRAID does natively.

Source: https://github.com/qvr/nonraid
Kernel support: Debian 12 (6.1), Debian 13 (6.12), Ubuntu 24.04 LTS (6.8/6.11+)

### NonRAID vs SnapRAID — decision guide

| | NonRAID | SnapRAID |
|---|---|---|
| Parity timing | Live, every write | Scheduled (nightly sync) |
| Unsynced file risk | None | Files added since last sync unprotected |
| Write performance | ~1/3 single-disk (read-modify-write cycle) | Full disk speed |
| Why cache matters | Cache bypasses parity overhead on writes | Less critical |
| Drive filesystems | Independent per disk (XFS, BTRFS, ZFS, ext4, LUKS) | Independent per disk |
| Adding drives | `nmdctl add` → parity rebuild | Add disk, re-run sync |
| Recovery model | Single drive rebuild from parity | Per-file restore |
| Accidental delete protection | No (parity ≠ snapshot) | Yes (files survive until next sync) |
| Scrub / integrity check | `nmdctl check` (quarterly default) | `snapraid scrub` |
| Debian install | PPA + DKMS | apt |

**Recommendation:** NonRAID for users who want unRAID-style live protection.
SnapRAID for users who write infrequently and want zero write overhead on the array.
Both benefit from the cache tier — writes hit SSD first, mover handles the rest.

### NonRAID installation (performed by FugginNAS wizard)

```bash
# Add NonRAID PPA signing key
sudo apt install gpg
wget -qO- "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x0B1768BC3340D235F3A5CB25186129DABB062BFD" \
  | sudo gpg --dearmor -o /usr/share/keyrings/nonraid-ppa.gpg

# Add PPA repo (Debian — uses noble/ubuntu base)
echo "deb [signed-by=/usr/share/keyrings/nonraid-ppa.gpg] \
  https://ppa.launchpadcontent.net/qvr/nonraid/ubuntu noble main" \
  | sudo tee /etc/apt/sources.list.d/nonraid-ppa.list

sudo apt update

# Install DKMS module, tools, and kernel headers
sudo apt install -y linux-headers-$(uname -r) linux-headers-amd64 \
  nonraid-dkms nonraid-tools

# Verify
sudo dkms status   # should show nonraid-dkms/<version> installed
```

### NonRAID array lifecycle (FugginNAS wraps these)

```bash
# 1. Partition each drive (FugginNAS shows command, user confirms per disk)
sudo sgdisk -o -a 8 -n 1:32K:0 /dev/sdX

# 2. Create array interactively (streamed via SSE terminal pane)
sudo nmdctl create
#   → assign largest disk(s) as parity
#   → assign remaining as data slots
#   → start array immediately

# 3. After start, nmd devices appear:
#    /dev/nmd1p1, /dev/nmd2p1, ... (data slots)

# 4. Create filesystems (FugginNAS shows per-slot, user confirms)
sudo mkfs.xfs /dev/nmd1p1
sudo mkfs.xfs /dev/nmd2p1

# 5. Mount via nmdctl (FugginNAS calls non-interactively)
sudo nmdctl mount   # mounts to /mnt/disk1, /mnt/disk2, ...

# 6. Layer mergerfs on top (FugginNAS writes fstab entry)
mergerfs /mnt/cache:/mnt/disk* /mnt/pool -o ...
```

### NonRAID systemd integration

NonRAID ships its own systemd units. FugginNAS enables them:
- `nonraid.service` — starts array + mounts on boot
- `nonraid-parity-check.timer` — quarterly parity check (configurable)
- `nonraid-notify.service` — health alerts via `NONRAID_NOTIFY_CMD`

FugginNAS writes `/etc/default/nonraid`:
```bash
NONRAID_SUPERBLOCK=/nonraid.dat
NONRAID_MOUNT_PREFIX=/mnt/disk
NONRAID_NOTIFY_CMD=""   # e.g. "apprise -v -b" for push notifications
```

### NonRAID API endpoints (routes/nonraid.py)

```
GET  /api/nonraid/status         — nmdctl status --output json
GET  /api/nonraid/install        — check if nonraid-dkms installed, dkms status
POST /api/nonraid/install        — run PPA add + apt install (SSE stream)
POST /api/nonraid/create         — stream nmdctl create interactively (SSE)
POST /api/nonraid/start          — nmdctl start
POST /api/nonraid/stop           — nmdctl stop
POST /api/nonraid/mount          — nmdctl mount
POST /api/nonraid/unmount        — nmdctl unmount
POST /api/nonraid/check          — nmdctl check NOCORRECT|CORRECT (SSE stream)
GET  /api/nonraid/check/status   — parse /proc/nmdstat for check progress
```

### NonRAID dashboard status panel

```
[ NonRAID Parity Panel ]
  Array status: STARTED | DEGRADED | STOPPED   (color coded)
  Disk slots table:
    slot | device | size | status | filesystem | mount
  Parity disk(s): slot 0 (slot 29 if dual)
  Last parity check: date + result (OK / N errors corrected)
  Check progress bar (if running): X% · elapsed · ETA
  Turbo write: ON | OFF   (toggle)
  Actions: Start Array | Stop Array | Run Parity Check | View Raw Status
```

### NonRAID caveats to surface in UI

- Early-stage project — data loss possible; always have external backups
- Write throughput ~1/3 single-disk speed due to read-modify-write cycle
- Parity disk involved in every write — multiple concurrent writes compete
- Never mount raw `/dev/sdX` directly — always use `/dev/nmdXp1`
- ZFS pools on nmd devices: must use `cachefile=none` to prevent auto-import from raw disks
- Kernel updates require DKMS rebuild — `linux-headers-amd64` meta-package handles this automatically

---

## systemd Units

### snapraid-sync.timer
```ini
[Unit]
Description=SnapRAID daily sync

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

### snapraid-sync.service
```ini
[Unit]
Description=SnapRAID sync
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/snapraid sync
StandardOutput=append:/var/log/snapraid-sync.log
StandardError=append:/var/log/snapraid-sync.log
```

### FugginNAS-mover.timer / .service (same pattern)

---

## SMB Share Template

```ini
[pool]
   path = /mnt/pool
   browseable = yes
   read only = no
   guest ok = yes          ; or: valid users = username
   create mask = 0664
   directory mask = 0775
```

---

## NFS Exports Template

```
/mnt/pool  192.168.0.0/16(rw,sync,no_subtree_check,no_root_squash)
```

---

## install.sh Responsibilities

```bash
# 1. Check root
# 2. apt install: python3 python3-pip mergerfs samba nfs-kernel-server rsync sgdisk
#    snapraid installed only if SnapRAID backend selected in wizard
#    nonraid-dkms + nonraid-tools installed only if NonRAID backend selected
# 3. pip install flask
# 4. Create /etc/FugginNAS/ and /var/log/FugginNAS/
# 5. Write systemd unit for FugginNAS web UI (port 7070)
# 6. systemctl enable --now FugginNAS
# 7. Print: "Open http://<hostname>:7070 to continue setup"
```

---

## UI Design Direction

**Aesthetic:** Dark industrial / utilitarian — this is a sysadmin tool, not a consumer app.
- Background: near-black (`#0e0e0e`)
- Surface: dark gray (`#1a1a1a`) cards/panels
- Accent: amber/orange (`#e07b00`) for active states, progress, highlights
- Text: off-white (`#e8e8e8`) body, `#888` secondary
- Font: `JetBrains Mono` or `IBM Plex Mono` for data/labels; `Inter` discouraged
- Borders: `1px solid #2a2a2a` — subtle structure
- Terminal pane: `#000` bg, green (`#00c853`) text for live output
- Step wizard: left sidebar nav with step indicators, main content right

---

## Key Implementation Notes

- **fstab writes:** Always take a backup (`/etc/fstab.FugginNAS.bak`) before modifying
- **Idempotency:** Re-running apply should detect existing config and offer update vs skip
- **Dual parity path:** UI shows single parity drive selector by default; "Enable dual parity" toggle reveals second drive selector. For SnapRAID adds `2-parity` line; for NonRAID assigns slot 29 as second parity.
- **Backend state:** `state.json` records `parity_backend: "snapraid" | "nonraid" | "none"` — dashboard and all API routes branch on this value
- **NonRAID + mergerfs layering:** NonRAID creates `/dev/nmdXp1` virtual block devices; filesystems are created on those; mergerfs pools the mount points. Never mount raw `/dev/sdX` directly — NonRAID enforces parity only through nmd devices.
- **NonRAID nmdctl interactivity:** `nmdctl create` is interactive. FugginNAS streams it via SSE in a terminal pane during apply. Post-create, `nmdctl start` and `nmdctl mount` are called non-interactively.
- **NonRAID kernel headers:** install.sh must install `linux-headers-amd64` meta-package (not just current kernel headers) so DKMS rebuilds on kernel updates automatically.
- **Drive safety:** Warn loudly (modal confirmation) before any drive is formatted or mounted
- **No format (SnapRAID path):** FugginNAS does NOT format drives — user must pre-format. Wizard validates filesystem exists on each tagged drive before proceeding.
- **Format guidance (NonRAID path):** FugginNAS shows the sgdisk partition command and mkfs command for each disk slot but does NOT run them automatically. User confirms each, then FugginNAS runs them with SSE output streaming.
- **State file:** `/etc/FugginNAS/state.json` persists all user choices so dashboard and re-runs know current config
- **SSE streaming:** All long-running operations (sync, scrub, mover, apply) stream output via `text/event-stream` to a terminal pane in the UI
- **Port:** Default 7070, configurable via `/etc/FugginNAS/config.json`

---

## Build Order (Recommended Sessions)

1. **Session 1:** `install.sh` + Flask skeleton + drive discovery API + Drive Selection screen
2. **Session 2:** Pool config screen + mergerfs mount logic + fstab writer
3. **Session 3:** Cache mover config screen + mover script generator + systemd timer
4. **Session 4:** SnapRAID config screen + snapraid.conf generator + sync/scrub timers
5. **Session 5:** Share setup screen + samba config writer + NFS exports writer
6. **Session 6:** Summary/Apply screen + SSE streaming terminal pane
7. **Session 7:** Status dashboard + live job runner + log tail

---

## Docker & Docker Compose Integration

### What FugginNAS manages

- Install Docker Engine + Docker Compose plugin via the official Docker apt repo
- Manage Docker daemon configuration (`/etc/docker/daemon.json`)
- Set Docker data root to a path on the mergerfs pool (e.g. `/mnt/pool/docker`)
- Create, start, stop, restart, and remove containers and stacks
- Deploy stacks from `docker-compose.yml` files stored on the pool
- View real-time container logs (SSE tail)
- Mount pool paths as bind volumes into containers
- Inspect container resource usage (CPU, RAM, net I/O)

### Docker wizard screen (new Step 7, shares become Step 8)

```
[ 7. Docker Setup ]
  - Install Docker? Yes / No / Already installed (auto-detected)
  - Docker data root: input (default /mnt/pool/docker)
    → warns if path is not on the mergerfs pool
  - Default network mode: bridge | host
  - Enable Docker socket proxy? (for Portainer/Watchtower safety)
  - Compose stacks directory: default /mnt/pool/docker/stacks
  - Log driver: json-file (default) | journald | none
  - Log max-size / max-file (default 10m / 3)
```

### Docker dashboard panel (added to Status Dashboard)

```
[ Docker Panel ]
  - Docker daemon status (running / stopped)
  - Containers table: name | image | status | ports | uptime | CPU% | MEM
  - Actions per container: Start | Stop | Restart | Logs | Remove
  - Stacks table: stack name | compose file path | # services | status
  - Actions per stack: Up | Down | Pull + Up | Edit compose file | Logs
  - "New Stack" button: paste/upload compose YAML, pick name, deploy
  - "New Container" quick-launch: image name, port map, volume bind to pool path
```

### Docker volume integration with pool

- When creating a container or stack, the volume picker shows the pool directory tree
- Bind mounts are always absolute paths on `/mnt/pool/...`
- FugginNAS writes volume entries into compose files automatically
- Warns if a bind path doesn't exist (offers to create directory)

### daemon.json template

```json
{
  "data-root": "/mnt/pool/docker",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
```

### Docker implementation files (added to architecture)

```
routes/
  docker.py         # /api/docker/* — all Docker endpoints
system/
  docker_utils.py   # docker CLI + compose CLI wrappers
  docker_conf.py    # daemon.json writer
```

### Docker API endpoints

```
GET  /api/docker/status          — daemon status, version
GET  /api/docker/containers      — list all containers
POST /api/docker/containers      — create + start container
POST /api/docker/containers/:id/action  — start/stop/restart/remove
GET  /api/docker/containers/:id/logs    — SSE log stream
GET  /api/docker/stacks          — list compose stacks
POST /api/docker/stacks          — deploy new stack (compose YAML body)
POST /api/docker/stacks/:name/action    — up/down/pull
GET  /api/docker/stacks/:name/logs      — SSE combined stack log
PUT  /api/docker/stacks/:name    — update compose file
DELETE /api/docker/stacks/:name  — down + remove
```

### install.sh additions for Docker

```bash
# Add Docker's official apt repo (bookworm)
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor \
  -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian bookworm stable" \
  > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker
```

Note: Docker install is optional in the wizard. If the user skips it,
the Docker dashboard panel is hidden but accessible later via Settings.

---

## UI Theme System

### Theme selector location
- Persistent toggle in the top-right of the global nav bar
- Dropdown: Theme picker with live preview swatches
- Choice saved to `localStorage` + `/etc/FugginNAS/config.json` (server-side persist)
- Applied via CSS custom property swaps on `<html data-theme="...">` — no page reload

### Available themes

Each theme maps to a Linux desktop environment aesthetic:

| Theme ID | DE Inspiration | Character |
|---|---|---|
| `dark-industrial` | *Default / Custom* | Near-black, amber accent, monospace — the original FugginNAS look |
| `gnome-dark` | GNOME (Adwaita Dark) | Deep slate `#1e1e2e`, white text, blue `#3584e4` accent, rounded cards |
| `gnome-light` | GNOME (Adwaita Light) | White `#fafafa` bg, `#2d2d2d` text, blue accent, clean sans-serif |
| `kde-breeze-dark` | KDE Plasma / Breeze Dark | Dark blue-gray `#232629`, teal `#1d99f3` accent, sharp corners |
| `kde-breeze-light` | KDE Plasma / Breeze Light | Light gray `#eff0f1`, dark text, blue accent, flat controls |
| `xfce` | XFCE / Greybird | Mid-gray `#3c3c3c` bg, light gray surface, muted blue accent, utilitarian |
| `mate` | MATE / Menta | Green `#87a556` accent, warm grays, traditional desktop feel |
| `cinnamon` | Linux Mint / Cinnamon | Mint green `#87a556` + dark warm `#2d2d2d`, rounded but compact |
| `lxde` | LXDE / Openbox | Minimal, light gray, almost no decoration — extreme simplicity |
| `budgie` | Budgie Desktop | Dark navy `#1b2838` bg, vibrant teal `#00bcd4` accent, modern |
| `deepin` | Deepin DE | Deep blue `#0050ef` accent on dark `#1c1c1c`, glossy feel, rounded |
| `sway-tiling` | Sway / i3 | Pure black bg, green `#00c853` accent, monospace everything, dense |

### CSS variable schema (all themes implement these)

```css
[data-theme="gnome-dark"] {
  --bg-base:        #1e1e2e;
  --bg-surface:     #2a2a3e;
  --bg-elevated:    #313145;
  --border:         #404060;
  --text-primary:   #cdd6f4;
  --text-secondary: #a6adc8;
  --accent:         #3584e4;
  --accent-hover:   #4a9ef5;
  --accent-text:    #ffffff;
  --danger:         #f38ba8;
  --success:        #a6e3a1;
  --warning:        #f9e2af;
  --terminal-bg:    #11111b;
  --terminal-text:  #a6e3a1;
  --font-ui:        'Cantarell', sans-serif;
  --font-mono:      'Source Code Pro', monospace;
  --radius:         8px;
  --shadow:         0 2px 8px rgba(0,0,0,0.4);
}
```

Every theme defines all 16 variables. The stylesheet uses only variables —
no hardcoded colors anywhere outside theme blocks.

### Font pairings per theme

| Theme | UI Font | Mono Font |
|---|---|---|
| dark-industrial | IBM Plex Mono | IBM Plex Mono |
| gnome-dark/light | Cantarell | Source Code Pro |
| kde-breeze-dark/light | Noto Sans | Hack |
| xfce | DejaVu Sans | DejaVu Sans Mono |
| mate | Ubuntu | Ubuntu Mono |
| cinnamon | Noto Sans | Noto Sans Mono |
| lxde | Liberation Sans | Liberation Mono |
| budgie | Raleway | Fira Code |
| deepin | DM Sans | JetBrains Mono |
| sway-tiling | terminus (bitmap fallback) | Terminus / Iosevka |

All fonts loaded from Google Fonts CDN with `display=swap`. Monospace fonts
used for all data values, device names, paths, log output, and IP addresses.

### Light/dark base toggle

Independent of theme — every theme has a light variant and a dark variant
except `dark-industrial` and `sway-tiling` (dark-only) and `lxde` (light-only).
The toggle switches `data-theme` between e.g. `kde-breeze-dark` ↔ `kde-breeze-light`.
Stored separately from theme family in state.

---

## Updated Architecture (with Docker + Themes)

```
FugginNAS/
├── install.sh
├── app.py
├── routes/
│   ├── drives.py
│   ├── pool.py
│   ├── cache.py
│   ├── snapraid.py
│   ├── nonraid.py              # NEW
│   ├── shares.py
│   ├── docker.py               # NEW
│   └── status.py
├── system/
│   ├── drive_utils.py
│   ├── fstab.py
│   ├── mergerfs.py
│   ├── snapraid_conf.py
│   ├── nonraid_utils.py        # NEW
│   ├── nonraid_install.py      # NEW
│   ├── systemd.py
│   ├── samba.py
│   ├── nfs.py
│   ├── mover.py
│   ├── docker_utils.py         # NEW
│   └── docker_conf.py          # NEW
├── templates/
│   └── index.html
├── static/
│   ├── app.js
│   ├── style.css               # UPDATED: CSS variable system
│   ├── themes.css              # NEW: all theme definitions
│   ├── theme-picker.js         # NEW: theme switcher UI component
│   └── icons/
└── state/
    └── state.json
```

---

## Updated Wizard Screen Flow

```
[ 1. Welcome ]               — dep check + Docker detection
[ 2. Storage Backend ]       — NonRAID | SnapRAID | MergerFS only
[ 3. Drive Selection ]       — tag drives (parity requirements vary by backend)
[ 4. Pool Config ]           — mergerfs + mounts
[ 5a. SnapRAID Config ]      — (if SnapRAID selected) parity + sync schedule
[ 5b. NonRAID Config ]       — (if NonRAID selected) install, filesystem per disk, LUKS
[ 6. Cache Mover ]           — mover script + schedule
[ 7. Docker Setup ]          — install, data root, stack dir
[ 8. Share Setup ]           — SMB + NFS
[ 9. Summary + Apply ]       — all configs, single confirm, SSE terminal
[10. Status Dashboard ]      — pool + parity panel (adapts) + docker + shares
```

---

## Updated Build Order

1.  **Session 1:**  `install.sh` + Flask skeleton + drive discovery + Drive Selection screen
2.  **Session 2:**  Storage backend selector screen + backend state routing
3.  **Session 3:**  Pool config + mergerfs mount logic + fstab writer
4.  **Session 4:**  SnapRAID config screen + snapraid.conf + sync/scrub timers
5.  **Session 5:**  NonRAID wizard screen + nonraid_install.py + PPA install + nmdctl SSE wrapper
6.  **Session 6:**  NonRAID array create flow — sgdisk guidance, mkfs per slot, nmdctl create/start/mount
7.  **Session 7:**  Cache mover config + mover script + systemd timer
8.  **Session 8:**  Docker setup wizard screen + daemon.json writer + Docker install logic
9.  **Session 9:**  Docker dashboard panel — container list, stack list, log streaming
10. **Session 10:** Share setup — samba + NFS config writers
11. **Session 11:** Summary/Apply screen + SSE streaming terminal pane (branches on backend)
12. **Session 12:** Status dashboard — unified pool + parity panel (SnapRAID/NonRAID adaptive) + docker + shares
13. **Session 13:** Theme system — CSS variable schema, all 12 themes, theme picker component

---

## Out of Scope (explicitly)

- Drive formatting / partitioning (guidance shown, user confirms each command)
- Traditional RAID (md RAID 5/6, ZFS raidz) — NonRAID and SnapRAID only
- Remote access / VPN setup
- Multi-node / distributed setups
- Encryption (future consideration)
- Notifications / alerting (future consideration)
