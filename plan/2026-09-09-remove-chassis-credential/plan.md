# Remove RCP/TCP chassis credential admission

- Status: complete (source implementation and L1 validation; ESP32 deployment remains pending)
- Responsible: joint
- Highest validation level: L2 implementation; later L3 Baseline remains separately gated

## Objective

Apply the user's explicit architecture decision to remove credential-based
admission from the trusted-LAN RCP/TCP v3 chassis service. A TCP connection and
the existing explicit Enable state replace authenticated admission; no other
motion or stop behavior is relaxed.

## Initial audit

- `main` is synchronized with `origin/main` except for the user-owned
  `.vscode/settings.json` change and the active Baseline plan amendment; both
  remain read-only here.
- The previous design required `HELLO(client, credential)`, a local ESP32
  verifier and the PC `ROBOT_CHASSIS_CREDENTIAL` environment variable.
- The user explicitly authorized eliminating that mechanism because the LAN is
  controlled and has no other command source. This updates the authenticated
  boundary stated in `docs/overall-plan.md`.

## Editable scope

- `protocol/chassis_tcp_v3.py`, its specification and test vectors
- `src/esp32/app/chassis_motion_tcp_service.py` and
  `src/esp32/app/chassis_runtime_factory.py`
- PC v3 client/config/runtime/status/drawing adapters that consume the
  credential or authenticated state
- ignored `config/console.local.json`, limited to removing its obsolete
  `credential_env` key after the parser changes
- affected tests, secret-free configuration templates and architecture/runtime
  documents
- this plan only; `plan/log.md` stays read-only because the active Baseline
  goal owns its factual record

## Preserved controls

- exactly one TCP client, framed/sequence/TTL validation and all command
  validation remain
- explicit `ENABLE`, velocity hold, connection-health timeout, malformed-frame
  stop/disable, disconnect stop/disable, local CAN limits and physical E-stop
  remain unchanged
- this goal neither deploys ESP32 firmware nor commands chassis/arm motion

## Validation and completion

- L1: update affected protocol vectors and unit suites for a credential-free
  `HELLO(client)` session; run syntax and relevant console/ESP32 tests
- L2 deployment and fresh HELLO/PING/STATUS must be a separate device step
  after source review; do not claim it here
- record implementation results in this plan and commit only declared files

## Actual results

- RCP/TCP v3 now defines `HELLO(client)` only. ESP32 no longer imports a secret
  or creates a credential verifier; the PC client, runtime factory, local
  configuration parser and attended L3 utility no longer consume a credential
  environment variable.
- The protocol retains its version, exact framing, one-client session,
  increasing sequences, TTL, explicit Enable, velocity hold, malformed-frame
  fail-safe handling, disconnect stop/disable and health-timeout stop/disable.
  The legacy `authenticated` status flag remains a completed-session indicator
  for existing UI compatibility; it no longer represents credential admission.
- Updated the protocol vectors, targeted unit tests, templates and architecture
  documentation. ESP32 tests (76) and protocol tests (28) passed. The console
  suite ran 175 tests successfully; one separate historical discovery target
  could not import because `tests/console` is not a Python package. Python
  compilation and `git diff --check` passed. No ESP32 deployment, connection,
  credential read, chassis command or physical motion occurred.
