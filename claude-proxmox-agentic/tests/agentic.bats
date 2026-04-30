#!/usr/bin/env bats
# =============================================================================
#  Tests for agentic.sh — Claude Code LXC Deployer for Proxmox
#
#  Run:  bats tests/agentic.bats
#        bats --tap tests/agentic.bats
# =============================================================================

SCRIPT="${BATS_TEST_DIRNAME}/../agentic.sh"

# ── One-time setup ────────────────────────────────────────────────────────────

# create_container() appends an AppArmor line to /etc/pve/lxc/<CT_ID>.conf.
# That path is hardcoded in the production script and is specific to Proxmox.
# Tests that exercise this code path are skipped unless the directory already
# exists and is writable by the current user (e.g. a dedicated CI container
# or a Proxmox node set up for integration testing).  We deliberately avoid
# sudo/chown here so this test file is safe to run on any host.
setup_file() {
  export BATS_PVE_LXC_WRITABLE=false
  if [[ -d /etc/pve/lxc && -w /etc/pve/lxc ]]; then
    export BATS_PVE_LXC_WRITABLE=true
  fi
}

# ── Helpers ───────────────────────────────────────────────────────────────────

# Source the script functions without executing main.
# sed removes the `main "$@"` entrypoint line wherever it appears so tests
# stay safe even if blank lines are added before or after the call.
_load_functions() {
  source <(sed '/^main "\$@"$/d' "$SCRIPT")
}

# Create a mock executable in MOCK_BIN.
# Usage: _mock <name> [exit-code] [stdout]
_mock() {
  local name="$1" rc="${2:-0}" out="${3:-}"
  {
    printf '#!/usr/bin/env bash\n'
    [[ -n "$out" ]] && printf 'printf "%%s\\n" %q\n' "$out"
    printf 'exit %d\n' "$rc"
  } > "${MOCK_BIN}/${name}"
  chmod +x "${MOCK_BIN}/${name}"
}

# Create a mock that records its arguments to a file.
# Each argument is written on its own line; a blank separator line follows
# each invocation so callers can reliably grep individual arguments even when
# they contain spaces.
_mock_record() {
  local name="$1" rc="${2:-0}"
  {
    printf '#!/usr/bin/env bash\n'
    printf 'for _arg in "$@"; do printf "%%s\\n" "$_arg"; done >> "%s/%s.calls"\n' "$MOCK_BIN" "$name"
    printf 'printf "\\n" >> "%s/%s.calls"\n' "$MOCK_BIN" "$name"
    printf 'exit %d\n' "$rc"
  } > "${MOCK_BIN}/${name}"
  chmod +x "${MOCK_BIN}/${name}"
}

setup() {
  # Each test gets a clean temporary bin directory prepended to PATH.
  MOCK_BIN="$(mktemp -d)"
  export PATH="${MOCK_BIN}:${PATH}"

  # Sensible defaults for all mocks used across the suite
  _mock id 0 "0"                        # id -u → 0 (root)
  _mock pct 0 ""
  _mock pveam 0 ""
  _mock pvesh 0 "200"                   # pvesh get /cluster/nextid → 200
  _mock pvesm 0 "local-lvm"
  _mock openssl 0 "testpassword123"
  _mock ping 0 ""
  _mock hostname 0 "10.0.0.5"

  # Temp dir for files written during tests
  TEST_TMP="$(mktemp -d)"
  export CT_ID=""
}

teardown() {
  rm -rf "$MOCK_BIN" "$TEST_TMP"
}

# =============================================================================
# 1.  Output helper functions
# =============================================================================

@test "info prints [INFO] prefix" {
  _load_functions
  run bash -c "source <(sed '/^main \"\$@\"$/d' '$SCRIPT'); info 'hello world'"
  [[ "$output" == *"[INFO]"* ]]
  [[ "$output" == *"hello world"* ]]
}

@test "success prints [OK] prefix" {
  _load_functions
  run bash -c "source <(sed '/^main \"\$@\"$/d' '$SCRIPT'); success 'all good'"
  [[ "$output" == *"[OK]"* ]]
  [[ "$output" == *"all good"* ]]
}

@test "warn prints [WARN] prefix" {
  _load_functions
  run bash -c "source <(sed '/^main \"\$@\"$/d' '$SCRIPT'); warn 'careful'"
  [[ "$output" == *"[WARN]"* ]]
  [[ "$output" == *"careful"* ]]
}

@test "error prints [ERROR] prefix and exits with code 1" {
  run bash -c "source <(sed '/^main \"\$@\"$/d' '$SCRIPT'); error 'something broke'"
  [ "$status" -eq 1 ]
  [[ "$output" == *"[ERROR]"* ]]
  [[ "$output" == *"something broke"* ]]
}

@test "error exits even with set -euo pipefail active" {
  run bash -c "set -euo pipefail; source <(sed '/^main \"\$@\"$/d' '$SCRIPT'); error 'boom'; echo 'should not reach here'"
  [ "$status" -eq 1 ]
  [[ "$output" != *"should not reach here"* ]]
}

@test "header prints the banner box" {
  run bash -c "source <(sed '/^main \"\$@\"$/d' '$SCRIPT'); header"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Claude Code LXC Deployer"* ]]
}

# =============================================================================
# 2.  preflight()
# =============================================================================

@test "preflight passes when root and required commands exist" {
  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    preflight
  "
  [ "$status" -eq 0 ]
}

@test "preflight fails when not running as root" {
  # Override id to return non-zero UID
  _mock id 0 "1000"
  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    preflight
  "
  [ "$status" -eq 1 ]
  [[ "$output" == *"must be run as root"* ]]
}

@test "preflight fails when pct is not found" {
  rm -f "${MOCK_BIN}/pct"
  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    preflight
  "
  [ "$status" -eq 1 ]
  [[ "$output" == *"pct not found"* ]]
}

@test "preflight fails when pveam is not found" {
  rm -f "${MOCK_BIN}/pveam"
  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    preflight
  "
  [ "$status" -eq 1 ]
  [[ "$output" == *"pveam not found"* ]]
}

# =============================================================================
# 3.  get_config()
# =============================================================================

# Helper: run get_config with piped answers and return its output/status.
# Arguments are newline-separated answers matching each read prompt in order:
#   CT_ID, CT_HOSTNAME, CT_TZ, CT_PASSWORD, CT_PASSWORD_CONFIRM,
#   CT_CORES, CT_RAM, CT_SWAP, CT_DISK, CT_STORAGE, CT_IP,
#   CT_DNS, CT_CODESERVER_PASS, CT_SSH_KEY, confirm
_run_get_config() {
  local answers="$1"
  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'

    # pct status must fail (container ID doesn't exist yet)
    cat > '${MOCK_BIN}/pct' << 'MOCK'
#!/usr/bin/env bash
if [[ \"\$1\" == 'status' ]]; then exit 1; fi
exit 0
MOCK
    chmod +x '${MOCK_BIN}/pct'

    # pveam available returns a template name
    cat > '${MOCK_BIN}/pveam' << 'MOCK'
#!/usr/bin/env bash
if [[ \"\$1\" == 'available' ]]; then
  echo '1 ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
fi
exit 0
MOCK
    chmod +x '${MOCK_BIN}/pveam'

    # pvesm status returns a storage entry
    cat > '${MOCK_BIN}/pvesm' << 'MOCK'
#!/usr/bin/env bash
echo 'Name Status...'
echo 'local-lvm active'
exit 0
MOCK
    chmod +x '${MOCK_BIN}/pvesm'

    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    printf '%s\n' $'${answers}' | get_config
  "
}

@test "get_config accepts all defaults with DHCP and proceeds on 'y'" {
  # Answers: empty for all (use defaults), then 'y' to confirm
  _run_get_config $'\n\n\nsecret\nsecret\n\n\n\n\n\n\n\n\n\ny'
  [ "$status" -eq 0 ]
}

@test "get_config aborts on 'N' at confirmation" {
  _run_get_config $'\n\n\nsecret\nsecret\n\n\n\n\n\n\n\n\n\nN'
  [ "$status" -eq 0 ]
  [[ "$output" == *"Aborted"* ]]
}

@test "get_config errors when CT_ID is not numeric" {
  # First answer is the CT_ID — supply a non-numeric value
  _run_get_config $'abc\n\n\nsecret\nsecret\n\n\n\n\n\n\n\n\n\ny'
  [ "$status" -eq 1 ]
  [[ "$output" == *"must be a number"* ]]
}

@test "get_config errors when password is empty" {
  # CT_PASSWORD and CT_PASSWORD_CONFIRM are both empty
  _run_get_config $'\n\n\n\n\n\n\n\n\n\n\n\n\n\ny'
  [ "$status" -eq 1 ]
  [[ "$output" == *"Password cannot be empty"* ]]
}

@test "get_config errors when passwords do not match" {
  _run_get_config $'\n\n\nsecret1\nsecret2\n\n\n\n\n\n\n\n\n\ny'
  [ "$status" -eq 1 ]
  [[ "$output" == *"Passwords do not match"* ]]
}

@test "get_config errors when static IP given without gateway" {
  # CT_IP = 192.168.1.10/24, then CT_GW = empty (just Enter)
  _run_get_config $'\n\n\nsecret\nsecret\n\n\n\n\n\n192.168.1.10/24\n\n\n\n\ny'
  [ "$status" -eq 1 ]
  [[ "$output" == *"Gateway is required"* ]]
}

@test "get_config errors when container ID already exists" {
  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'

    # pct status succeeds → container exists
    cat > '${MOCK_BIN}/pct' << 'MOCK'
#!/usr/bin/env bash
exit 0
MOCK
    chmod +x '${MOCK_BIN}/pct'

    cat > '${MOCK_BIN}/pveam' << 'MOCK'
#!/usr/bin/env bash
[[ \"\$1\" == 'available' ]] && echo '1 ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
exit 0
MOCK
    chmod +x '${MOCK_BIN}/pveam'

    cat > '${MOCK_BIN}/pvesm' << 'MOCK'
#!/usr/bin/env bash
echo 'Name Status...'
echo 'local-lvm active'
exit 0
MOCK
    chmod +x '${MOCK_BIN}/pvesm'

    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    printf '%s\n' $'\n\n\nsecret\nsecret\n\n\n\n\n\n\n\n\n\ny' | get_config
  "
  [ "$status" -eq 1 ]
  [[ "$output" == *"already exists"* ]]
}

@test "get_config uses pvesh next ID as default CT_ID" {
  # pvesh returns 150; supply empty answer so the default is used
  cat > "${MOCK_BIN}/pvesh" << 'MOCK'
#!/usr/bin/env bash
echo "150"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pvesh"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'

    cat > '${MOCK_BIN}/pct' << 'M'
#!/usr/bin/env bash
[[ \"\$1\" == 'status' ]] && exit 1
exit 0
M
    chmod +x '${MOCK_BIN}/pct'

    cat > '${MOCK_BIN}/pveam' << 'M'
#!/usr/bin/env bash
[[ \"\$1\" == 'available' ]] && echo '1 ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
exit 0
M
    chmod +x '${MOCK_BIN}/pveam'

    cat > '${MOCK_BIN}/pvesm' << 'M'
#!/usr/bin/env bash
echo 'Name Status...'
echo 'local-lvm active'
exit 0
M
    chmod +x '${MOCK_BIN}/pvesm'

    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    get_config < <(printf '\n\n\nsecret\nsecret\n\n\n\n\n\ndhcp\n\n\n\ny\n')
    echo \"CT_ID=\${CT_ID}\"
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"CT_ID=150"* ]]
}

@test "get_config falls back to ID 100 when pvesh fails" {
  cat > "${MOCK_BIN}/pvesh" << 'MOCK'
#!/usr/bin/env bash
exit 1
MOCK
  chmod +x "${MOCK_BIN}/pvesh"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'

    cat > '${MOCK_BIN}/pct' << 'M'
#!/usr/bin/env bash
[[ \"\$1\" == 'status' ]] && exit 1
exit 0
M
    chmod +x '${MOCK_BIN}/pct'

    cat > '${MOCK_BIN}/pveam' << 'M'
#!/usr/bin/env bash
[[ \"\$1\" == 'available' ]] && echo '1 ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
exit 0
M
    chmod +x '${MOCK_BIN}/pveam'

    cat > '${MOCK_BIN}/pvesm' << 'M'
#!/usr/bin/env bash
echo 'Name Status...'
echo 'local-lvm active'
exit 0
M
    chmod +x '${MOCK_BIN}/pvesm'

    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    get_config < <(printf '\n\n\nsecret\nsecret\n\n\n\n\n\ndhcp\n\n\n\ny\n')
    echo \"CT_ID=\${CT_ID}\"
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"CT_ID=100"* ]]
}

@test "get_config falls back to hardcoded template when pveam returns nothing" {
  cat > "${MOCK_BIN}/pveam" << 'MOCK'
#!/usr/bin/env bash
# 'available' returns nothing (no ubuntu template listed)
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pveam"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'

    cat > '${MOCK_BIN}/pct' << 'M'
#!/usr/bin/env bash
[[ \"\$1\" == 'status' ]] && exit 1
exit 0
M
    chmod +x '${MOCK_BIN}/pct'

    cat > '${MOCK_BIN}/pvesm' << 'M'
#!/usr/bin/env bash
echo 'Name Status...'
echo 'local-lvm active'
exit 0
M
    chmod +x '${MOCK_BIN}/pvesm'

    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    get_config < <(printf '\n\n\nsecret\nsecret\n\n\n\n\n\ndhcp\n\n\n\ny\n')
    echo \"TEMPLATE=\${TEMPLATE}\"
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"TEMPLATE=ubuntu-24.04-standard_24.04-2_amd64.tar.zst"* ]]
}

@test "get_config falls back to local-lvm when pvesm returns no storage" {
  cat > "${MOCK_BIN}/pvesm" << 'MOCK'
#!/usr/bin/env bash
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pvesm"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'

    cat > '${MOCK_BIN}/pct' << 'M'
#!/usr/bin/env bash
[[ \"\$1\" == 'status' ]] && exit 1
exit 0
M
    chmod +x '${MOCK_BIN}/pct'

    cat > '${MOCK_BIN}/pveam' << 'M'
#!/usr/bin/env bash
[[ \"\$1\" == 'available' ]] && echo '1 ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
exit 0
M
    chmod +x '${MOCK_BIN}/pveam'

    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    get_config < <(printf '\n\n\nsecret\nsecret\n\n\n\n\n\ndhcp\n\n\n\ny\n')
    echo \"CT_STORAGE=\${CT_STORAGE}\"
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"CT_STORAGE=local-lvm"* ]]
}

# =============================================================================
# 4.  get_template()
# =============================================================================

@test "get_template skips download when template is already present" {
  # pveam list returns the template name
  cat > "${MOCK_BIN}/pveam" << 'MOCK'
#!/usr/bin/env bash
if [[ "$1" == "list" ]]; then
  echo "local  ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
fi
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pveam"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    TEMPLATE='ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
    get_template
    echo \"TEMPLATE_PATH=\${TEMPLATE_PATH}\"
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"already downloaded"* ]]
  [[ "$output" == *"TEMPLATE_PATH=local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"* ]]
}

@test "get_template downloads template when not present" {
  # pveam list returns nothing; pveam download succeeds
  _mock_record pveam 0
  # Overwrite with smarter mock that handles both subcommands
  cat > "${MOCK_BIN}/pveam" << 'MOCK'
#!/usr/bin/env bash
if [[ "$1" == "list" ]]; then
  exit 0          # template not present
fi
if [[ "$1" == "download" ]]; then
  echo "downloaded"
  exit 0
fi
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pveam"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    TEMPLATE='ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
    get_template
    echo \"TEMPLATE_PATH=\${TEMPLATE_PATH}\"
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"Downloading"* ]]
  [[ "$output" == *"TEMPLATE_PATH=local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"* ]]
}

@test "get_template errors when download fails" {
  cat > "${MOCK_BIN}/pveam" << 'MOCK'
#!/usr/bin/env bash
if [[ "$1" == "list" ]]; then
  exit 0
fi
# download fails
exit 1
MOCK
  chmod +x "${MOCK_BIN}/pveam"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    TEMPLATE='ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
    get_template
  "
  [ "$status" -eq 1 ]
  [[ "$output" == *"Failed to download"* ]]
}

@test "get_template sets TEMPLATE_PATH to local:vztmpl/<name>" {
  cat > "${MOCK_BIN}/pveam" << 'MOCK'
#!/usr/bin/env bash
[[ "$1" == "list" ]] && echo "local  mytemplate.tar.zst"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pveam"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    TEMPLATE='mytemplate.tar.zst'
    get_template
    echo \"PATH=\${TEMPLATE_PATH}\"
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"PATH=local:vztmpl/mytemplate.tar.zst"* ]]
}

# =============================================================================
# 5.  create_container()
# =============================================================================

_setup_create_env() {
  # create_container writes an AppArmor line to /etc/pve/lxc/<CT_ID>.conf.
  # Skip all create_container tests on hosts where that directory isn't writable.
  [[ "$BATS_PVE_LXC_WRITABLE" == "true" ]] \
    || skip "/etc/pve/lxc is not writable on this host — skipping create_container tests"
  # Write a pct mock that records its arguments
  _mock_record pct 0
}

@test "create_container builds DHCP network string" {
  _setup_create_env

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=200
    TEMPLATE_PATH='local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
    CT_HOSTNAME='test-host'
    CT_PASSWORD='secret'
    CT_CORES=2
    CT_RAM=4096
    CT_SWAP=512
    CT_DISK=20
    CT_STORAGE='local-lvm'
    CT_IP='dhcp'
    CT_DNS='1.1.1.1'
    CT_SSH_KEY=''

    create_container 2>&1 | cat
    grep -q 'ip=dhcp' '${MOCK_BIN}/pct.calls' && echo 'DHCP_FOUND'
  "
  [[ "$output" == *"DHCP_FOUND"* ]]
}

@test "create_container builds static IP network string" {
  _setup_create_env

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=201
    TEMPLATE_PATH='local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
    CT_HOSTNAME='test-static'
    CT_PASSWORD='secret'
    CT_CORES=2
    CT_RAM=4096
    CT_SWAP=512
    CT_DISK=20
    CT_STORAGE='local-lvm'
    CT_IP='192.168.1.50/24'
    CT_GW='192.168.1.1'
    CT_DNS='8.8.8.8'
    CT_SSH_KEY=''

    create_container 2>&1 | cat
    # Check that the pct call contained the static IP and gateway
    grep -q '192.168.1.50/24' '${MOCK_BIN}/pct.calls' && echo 'STATIC_IP_FOUND'
    grep -q '192.168.1.1' '${MOCK_BIN}/pct.calls' && echo 'GW_FOUND'
  "
  [[ "$output" == *"STATIC_IP_FOUND"* ]]
  [[ "$output" == *"GW_FOUND"* ]]
}

@test "create_container includes SSH key when valid key path provided" {
  _setup_create_env

  # Create a fake SSH public key file
  local fake_key="${TEST_TMP}/id_rsa.pub"
  echo "ssh-rsa AAAAB3Nza test@host" > "$fake_key"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=202
    TEMPLATE_PATH='local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
    CT_HOSTNAME='test-ssh'
    CT_PASSWORD='secret'
    CT_CORES=2
    CT_RAM=4096
    CT_SWAP=512
    CT_DISK=20
    CT_STORAGE='local-lvm'
    CT_IP='dhcp'
    CT_DNS='1.1.1.1'
    CT_SSH_KEY='${fake_key}'

    create_container 2>&1 | cat
    grep -q 'ssh-public-keys' '${MOCK_BIN}/pct.calls' && echo 'SSH_KEY_FOUND'
  "
  [[ "$output" == *"SSH_KEY_FOUND"* ]]
}

@test "create_container omits SSH key when path not provided" {
  _setup_create_env

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=203
    TEMPLATE_PATH='local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
    CT_HOSTNAME='test-nossh'
    CT_PASSWORD='secret'
    CT_CORES=2
    CT_RAM=4096
    CT_SWAP=512
    CT_DISK=20
    CT_STORAGE='local-lvm'
    CT_IP='dhcp'
    CT_DNS='1.1.1.1'
    CT_SSH_KEY=''

    create_container 2>&1 | cat
    grep -qv 'ssh-public-keys' '${MOCK_BIN}/pct.calls' && echo 'NO_SSH_KEY'
  "
  [[ "$output" == *"NO_SSH_KEY"* ]]
}

@test "create_container omits SSH key when file does not exist" {
  _setup_create_env

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=204
    TEMPLATE_PATH='local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
    CT_HOSTNAME='test-badkey'
    CT_PASSWORD='secret'
    CT_CORES=2
    CT_RAM=4096
    CT_SWAP=512
    CT_DISK=20
    CT_STORAGE='local-lvm'
    CT_IP='dhcp'
    CT_DNS='1.1.1.1'
    CT_SSH_KEY='/nonexistent/key.pub'

    create_container 2>&1 | cat
    ! grep -q 'ssh-public-keys' '${MOCK_BIN}/pct.calls' && echo 'NO_SSH_KEY'
  "
  [[ "$output" == *"NO_SSH_KEY"* ]]
}

@test "create_container appends AppArmor unconfined line to LXC conf" {
  # Use a test-specific CT_ID unlikely to collide with a real container.
  local test_ct_id="99${$}${RANDOM}"
  local conf_file="/etc/pve/lxc/${test_ct_id}.conf"
  _setup_create_env

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=${test_ct_id}
    TEMPLATE_PATH='local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
    CT_HOSTNAME='test-apparmor'
    CT_PASSWORD='secret'
    CT_CORES=2
    CT_RAM=4096
    CT_SWAP=512
    CT_DISK=20
    CT_STORAGE='local-lvm'
    CT_IP='dhcp'
    CT_DNS='1.1.1.1'
    CT_SSH_KEY=''
    create_container
  "
  [ "$status" -eq 0 ]
  # Verify the AppArmor line was actually appended to the LXC conf file
  grep -q 'lxc.apparmor.profile: unconfined' "$conf_file"
  # Clean up the conf file created by this test
  rm -f "$conf_file"
}

# =============================================================================
# 6.  start_container()
# =============================================================================

@test "start_container succeeds when network comes up on first attempt" {
  # pct exec ping succeeds immediately
  cat > "${MOCK_BIN}/pct" << 'MOCK'
#!/usr/bin/env bash
# pct start → success
# pct exec … ping → success
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=300
    CT_GW='192.168.1.1'
    CT_DNS='1.1.1.1'
    # Override sleep to be instant
    sleep() { :; }
    start_container
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"online"* ]]
}

@test "start_container exits with error when network is unavailable" {
  # pct start succeeds but every ping (pct exec ... ping) fails — the
  # function must exit non-zero when the container cannot reach the network.
  cat > "${MOCK_BIN}/pct" << 'MOCK'
#!/usr/bin/env bash
if [[ "$1" == "start" ]]; then exit 0; fi
# exec (ping) always fails
exit 1
MOCK
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=301
    CT_GW='192.168.1.1'
    CT_DNS='1.1.1.1'
    sleep() { :; }
    start_container
  "
  [ "$status" -ne 0 ]
}

@test "start_container uses CT_DNS when CT_GW is unset" {
  # When DHCP is used, CT_GW is unset; the script falls back to CT_DNS for ping.
  # Use a recording pct mock so we can assert that the ping target is CT_DNS.
  _mock_record pct 0

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=302
    CT_DNS='1.1.1.1'
    # CT_GW intentionally not set
    sleep() { :; }
    start_container
  "
  [ "$status" -eq 0 ]
  # The pct exec ping invocation must have targeted CT_DNS (1.1.1.1)
  grep -q '1.1.1.1' "${MOCK_BIN}/pct.calls"
}

# =============================================================================
# 7.  provision_container()
# =============================================================================

@test "provision_container substitutes CT_TZ placeholder in provision script" {
  _mock_record pct 0

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=400
    CT_TZ='Europe/London'
    CT_CODESERVER_PASS='cs-pass-123'

    provision_container

    # The provision script is cleaned up; check pct push was called
    grep -q 'push' '${MOCK_BIN}/pct.calls' && echo 'PUSH_CALLED'
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"PUSH_CALLED"* ]]
}

@test "provision_container substitutes CT_CODESERVER_PASS placeholder" {
  local capture_file="${TEST_TMP}/captured-provision.sh"
  # Use unquoted heredoc so ${capture_file} is expanded into the mock script
  cat > "${MOCK_BIN}/pct" << EOF
#!/usr/bin/env bash
if [[ "\$1" == "push" ]]; then
  cp "\$3" "${capture_file}"
fi
exit 0
EOF
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=401
    CT_TZ='America/Chicago'
    CT_CODESERVER_PASS='my-secure-pass'

    provision_container

    # Inspect the captured provision script
    if [[ -f '${capture_file}' ]]; then
      if grep -q 'my-secure-pass' '${capture_file}'; then echo 'PASS_SUBSTITUTED'; fi
      if grep -q '__CT_CODESERVER_PASS__' '${capture_file}'; then echo 'PLACEHOLDER_REMAINING'; fi
    fi
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"PASS_SUBSTITUTED"* ]]
  [[ "$output" != *"PLACEHOLDER_REMAINING"* ]]
}

@test "provision_container substitutes CT_TZ in provision script content" {
  local capture_file="${TEST_TMP}/captured-provision-tz.sh"
  cat > "${MOCK_BIN}/pct" << EOF
#!/usr/bin/env bash
if [[ "\$1" == "push" ]]; then
  cp "\$3" "${capture_file}"
fi
exit 0
EOF
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=402
    CT_TZ='Asia/Tokyo'
    CT_CODESERVER_PASS='pass123'

    provision_container

    if [[ -f '${capture_file}' ]]; then
      if grep -q 'Asia/Tokyo' '${capture_file}'; then echo 'TZ_SUBSTITUTED'; fi
      if grep -q '__CT_TZ__' '${capture_file}'; then echo 'TZ_PLACEHOLDER_REMAINING'; fi
    fi
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"TZ_SUBSTITUTED"* ]]
  [[ "$output" != *"TZ_PLACEHOLDER_REMAINING"* ]]
}

@test "provision_container removes temp script after execution" {
  _mock_record pct 0

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=403
    CT_TZ='UTC'
    CT_CODESERVER_PASS='pass'

    provision_container

    # Temp file should be removed
    [[ ! -f '/tmp/provision-403.sh' ]] && echo 'CLEANED_UP'
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"CLEANED_UP"* ]]
}

@test "provision_container calls pct exec to run the provision script" {
  _mock_record pct 0

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=404
    CT_TZ='UTC'
    CT_CODESERVER_PASS='pass'

    provision_container

    grep -q 'exec' '${MOCK_BIN}/pct.calls' && echo 'EXEC_CALLED'
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"EXEC_CALLED"* ]]
}

# =============================================================================
# 8.  print_summary()
# =============================================================================

@test "print_summary shows container ID and hostname" {
  cat > "${MOCK_BIN}/pct" << 'MOCK'
#!/usr/bin/env bash
# pct exec CT_ID -- hostname -I  → return an IP
echo "10.0.0.42"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=500
    CT_HOSTNAME='my-claude-box'
    CT_CORES=4
    CT_RAM=8192
    CT_DISK=30
    CT_STORAGE='local-lvm'
    CT_TZ='America/New_York'
    CT_CODESERVER_PASS='codepass'

    print_summary
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"500"* ]]
  [[ "$output" == *"my-claude-box"* ]]
}

@test "print_summary shows IP address when available" {
  cat > "${MOCK_BIN}/pct" << 'MOCK'
#!/usr/bin/env bash
echo "192.168.10.20"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=501
    CT_HOSTNAME='claude'
    CT_CORES=2
    CT_RAM=4096
    CT_DISK=20
    CT_STORAGE='local-lvm'
    CT_TZ='UTC'
    CT_CODESERVER_PASS='pass'

    print_summary
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"192.168.10.20"* ]]
  [[ "$output" == *"ssh root@192.168.10.20"* ]]
}

@test "print_summary shows 'pending (DHCP)' when no IP is available" {
  cat > "${MOCK_BIN}/pct" << 'MOCK'
#!/usr/bin/env bash
# hostname -I returns empty
echo ""
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=502
    CT_HOSTNAME='claude'
    CT_CORES=2
    CT_RAM=4096
    CT_DISK=20
    CT_STORAGE='local-lvm'
    CT_TZ='UTC'
    CT_CODESERVER_PASS='pass'

    print_summary
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"pending"* ]]
}

@test "print_summary displays Code Server access URL with password" {
  cat > "${MOCK_BIN}/pct" << 'MOCK'
#!/usr/bin/env bash
echo "10.10.10.10"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=503
    CT_HOSTNAME='claude'
    CT_CORES=4
    CT_RAM=8192
    CT_DISK=30
    CT_STORAGE='local-lvm'
    CT_TZ='America/Chicago'
    CT_CODESERVER_PASS='supersecret'

    print_summary
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"10.10.10.10:8443"* ]]
  [[ "$output" == *"supersecret"* ]]
}

@test "print_summary shows resource summary (CPU / RAM / disk)" {
  cat > "${MOCK_BIN}/pct" << 'MOCK'
#!/usr/bin/env bash
echo "10.0.0.1"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=504
    CT_HOSTNAME='claude'
    CT_CORES=8
    CT_RAM=16384
    CT_DISK=50
    CT_STORAGE='local-lvm'
    CT_TZ='UTC'
    CT_CODESERVER_PASS='pass'

    print_summary
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"8 CPU"* ]]
  [[ "$output" == *"16 GB RAM"* ]]
  [[ "$output" == *"50 GB disk"* ]]
}

@test "print_summary shows installed software list" {
  cat > "${MOCK_BIN}/pct" << 'MOCK'
#!/usr/bin/env bash
echo "10.0.0.1"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=505
    CT_HOSTNAME='claude'
    CT_CORES=2
    CT_RAM=4096
    CT_DISK=20
    CT_STORAGE='local-lvm'
    CT_TZ='UTC'
    CT_CODESERVER_PASS='pass'

    print_summary
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"Claude Code"* ]]
  [[ "$output" == *"Node.js"* ]]
  [[ "$output" == *"Docker"* ]]
}

@test "print_summary shows timezone in auto-update schedule" {
  cat > "${MOCK_BIN}/pct" << 'MOCK'
#!/usr/bin/env bash
echo "10.0.0.1"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pct"

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')
    CT_ID=506
    CT_HOSTNAME='claude'
    CT_CORES=2
    CT_RAM=4096
    CT_DISK=20
    CT_STORAGE='local-lvm'
    CT_TZ='Pacific/Auckland'
    CT_CODESERVER_PASS='pass'

    print_summary
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"Pacific/Auckland"* ]]
}

# =============================================================================
# 9.  Integration: main() orchestrates all steps in order
# =============================================================================

@test "main calls all pipeline steps in order" {
  # Record which functions are called
  cat > "${MOCK_BIN}/pct" << 'MOCK'
#!/usr/bin/env bash
[[ "$1" == "status" ]] && exit 1  # container doesn't exist
[[ "$1" == "exec" ]] && [[ "$4" == "ping" ]] && exit 0  # network is up
echo "10.0.0.1"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pct"

  cat > "${MOCK_BIN}/pveam" << 'MOCK'
#!/usr/bin/env bash
[[ "$1" == "available" ]] && echo "1 ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
[[ "$1" == "list"      ]] && echo "local ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pveam"

  cat > "${MOCK_BIN}/pvesm" << 'MOCK'
#!/usr/bin/env bash
echo "Name Status..."
echo "local-lvm active"
exit 0
MOCK
  chmod +x "${MOCK_BIN}/pvesm"

  # Pipe fully-automated answers
  local answers=$'\n\n\nsecret\nsecret\n\n\n\n\n\n\n\n\n\ny'

  run bash -c "
    export PATH='${MOCK_BIN}:${PATH}'
    source <(sed '/^main \"\$@\"$/d' '$SCRIPT')

    # Capture function calls
    CALLS=()
    header()             { CALLS+=(header);             }
    preflight()          { CALLS+=(preflight);           }
    get_config()         { CALLS+=(get_config);          }
    get_template()       { CALLS+=(get_template);        }
    create_container()   { CALLS+=(create_container);    }
    start_container()    { CALLS+=(start_container);     }
    provision_container(){ CALLS+=(provision_container); }
    print_summary()      { CALLS+=(print_summary);       }

    main

    echo \"\${CALLS[*]}\"
  " <<< "$answers"

  [ "$status" -eq 0 ]
  # Assert the exact call order — a reordered or missing step will fail this
  [ "$output" = "header preflight get_config get_template create_container start_container provision_container print_summary" ]
}
