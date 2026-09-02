# ESP32 RCP/TCP v2 L2 Deployment Record

> Historical record only. RCP/TCP v3 replaced this deployed contract and
> removed its acquire/heartbeat/release lease fields. Do not use this record as
> a current deployment manifest.

## Scope

This is the first resident deployment of the direct computer-to-ESP32 RCP/TCP
v2 listener. It is an L2, non-motion deployment only.

The device starts its development-network bootstrap and then the
version-controlled application entry point. When the ignored local device
configuration selects `tcp_v2_l2`, the listener composes `NoMotionChassis`.
It does not construct CAN, motors, PS2, UART, or servo objects.

## Verified device behavior

- The resident listener accepts a computer TCP connection after reset.
- A valid authenticated session returned `WELCOME`, `PONG`, and `STATE` with
  consecutive request sequences `1`, `2`, and `3`.
- `STATE` reported `service_state=ready`, `chassis_state=disabled`,
  `motion_permitted=false`, and `lease_active=false`.
- A syntactically valid but wrong credential returned
  `authentication_failed`.
- After that rejected connection was closed, a valid session connected and
  queried status again successfully.
- The console runtime completed the safe hardware sequence
  `connect -> status -> disconnect`.

The credential, endpoint address, and local console configuration are kept in
ignored local files and are not recorded here.

## Safety boundary

This deployment is not a chassis-motion release. It admits no L3 test, CAN
initialization, lease acquisition, motor enable, velocity, stop, or controller
integration. A later L3 goal must separately implement and validate the CAN
composition, physical stop behavior, heartbeat loss behavior, and all motion
safety gates.

## Operational note

The resident listener owns the normal run loop. Entering a serial REPL during
an active session can interrupt the service, so use it only for deliberate
maintenance with the applicable on-site safety gate. Restarting the device
returns it to the same selected L2 no-motion composition.
