# Remove Chassis Lease Layer

- Status: `complete (local source only; device deployment pending)`
- Responsible: `agent`
- Highest validation level: `L1`; device deployment remains pending

## Objective

Remove `ACQUIRE`, `HEARTBEAT`, and `RELEASE` from the active computer-to-ESP32
chassis protocol and all computer/UI surfaces. An authenticated TCP connection
is the single controller. Operators use only `ENABLE`, motion, `STOP`, and
`DISABLE`; link-health polling remains an internal background concern.

## Initial workspace state

```text
## main...origin/main
 M .vscode/settings.json
```

The `.vscode/settings.json` change belongs to the user, is unrelated to this
goal, and must not be modified, staged, or committed. Work continues on
`target/remove-chassis-lease`.

## Editable scope

- active chassis protocol module, vectors, schema documentation, and tests
- `src/esp32/app/` active chassis service/composition and focused tests
- `src/console/` chassis client, runtime configuration, controller/UI bindings,
  router, and focused tests
- committed configuration examples and chassis/console/overall documentation
- ignored `config/console.local.json`, limited to the lease-free manual-control
  field migration; endpoint and credential fields remain unchanged
- this plan and `plan/log.md`

## Read-only scope

- `.vscode/settings.json`
- `ESP32/`, `Camera/`, and `Robot Arm_Claws/`
- MaixCam, robot-arm, TCP232, network addresses, credentials, CAN assignments,
  physical limits, and device-local ignored configuration except for read-only
  compatibility review
- ignored ESP32 device configuration and every real device filesystem during
  this L1 implementation

## Shared dependencies and decisions

- The runtime boundary remains computer -> ESP32 TCP -> CAN -> chassis.
- The server continues to process exactly one TCP client at a time.
- Authentication remains part of connection establishment.
- `STOP` keeps an authenticated session enabled; `DISABLE` stops and de-energizes
  motors without closing TCP; disconnect or health timeout stops and disables.
- A bounded velocity hold remains: missing velocity refresh stops motion but
  leaves the session enabled.
- The breaking wire-contract revision will identify itself as RCP/TCP v3 so an
  old resident v2 service cannot be mistaken for the new implementation.

## Expected work

1. Define RCP/TCP v3 without lease commands or lease status fields.
2. Replace ESP32 ownership checks with authenticated-session checks and add an
   internal link-health timeout refreshed by valid authenticated traffic.
3. Replace console lease renewal with background `PING`; simplify UI state and
   controls to Connect, Enable, Disable, Stop, and velocity controls.
4. Remove lease settings and active router/API entries, update tests and docs,
   and verify that no active runtime reference remains.
5. Run focused and whole-subsystem L1 validation. Do not deploy or move hardware.

## Validation

- protocol vectors and protocol tests
- ESP32 service, runtime, CAN/chassis tests
- console client/runtime/controller/UI tests and offscreen smoke
- Python compilation, workspace validation, `git diff --check`, secret audit,
  and final Git status

## Deployment and residual risk

The currently deployed ESP32 remains RCP/TCP v2 until a separately authorized
device deployment. The new v3 computer client must not be used for real control
until matching ESP32 source and local configuration are deployed and accepted
through L2, followed by a separately confirmed L3 motion test.

## Actual result

- RCP/TCP v3 rejects the removed `ACQUIRE`, `HEARTBEAT`, and `RELEASE`
  message types and no longer reports lease fields in `STATE`.
- ESP32 accepts `ENABLE` immediately after an authenticated `HELLO`. `STOP`
  preserves enablement; `DISABLE` preserves the TCP session; disconnect or a
  2-second default connection-health timeout stops, disables, and ends the
  session. Velocity-hold expiry stops without disabling.
- The computer client, router, background runtime, UI state, and visible
  chassis panel expose only Connect/Disconnect, Enable/Disable, Stop, and
  velocity. Background health uses coalesced `PING` requests.
- The ignored local console configuration was migrated to schema 2 without
  printing or changing its endpoint values. No ESP32 local configuration or
  device filesystem was changed.

## Actual validation

- Focused changed-path suite: 61 passed.
- Full isolated suites: protocol 28 passed plus 6 subtests; ESP32 54 passed
  plus 2 subtests; console 49 passed; development 25 passed; MaixCam 53 passed;
  robot arm 16 passed. MaixCam and robot-arm sources were reviewed as
  unaffected by this direct computer-to-ESP32 contract change.
- Python source check: 36 files passed.
- Offscreen console smoke construction passed.
- Ignored local console configuration schema-2 load passed.
- `git diff --check` passed. No hardware connection, deployment, or motion test
  was run.

## Intent to submit

```text
refactor(chassis): remove lease control layer
```
