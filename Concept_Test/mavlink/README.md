# MAVLink on Arduino UNO Q

This implements MAVLink as a **companion-computer bridge**, which fits UNO Q's
dual-processor design:

- **MCU (STM32, `mcu_sketch.ino`)** — real-time sensor/actuator I/O, exposed
  to Linux over the `Bridge` RPC library. No MAVLink code here.
- **MPU (Linux, `main.py`)** — owns the actual MAVLink protocol using
  `pymavlink`: heartbeats, telemetry, and command handling, talking to a
  ground station over UDP.

```
GCS (QGroundControl) <--UDP/MAVLink--> main.py (MPU/Linux) <--Bridge RPC--> mcu_sketch.ino (MCU)
```

## Setup

1. **Install pymavlink on the Linux side.** Open the App Lab console (or SSH
   into the board) and run:
   ```
   pip install pymavlink --break-system-packages
   ```
2. **Create an App Lab project**, put `mcu_sketch.ino` in the sketch folder
   and `main.py` in the Python folder (App Lab's project wizard sets this
   structure up for you — drop the file contents in rather than the raw
   folders above).
3. **Wire your hardware:**
   - None needed — this uses the UNO Q's built-in LED (`LED_BUILTIN`).
   - Board is powered over USB, so there's no battery telemetry — the bridge
     sends `HEARTBEAT` and handles incoming relay (on/off) commands.
4. **Point `MAV_TARGET` in `main.py`** at your GCS. `udpout:127.0.0.1:14550`
   assumes QGroundControl/Mission Planner runs on the same board or you're
   testing locally; use the GCS machine's real IP on your network otherwise.
5. **Run the app** from App Lab, or `python3 main.py` from the Debian shell.
6. **In QGroundControl/Mission Planner**, add a UDP connection on port 14550.
   You should see a heartbeat and a "generic" vehicle appear.

## Verifying it end-to-end

- `mavproxy.py --master=udpin:0.0.0.0:14550` from another machine is a handy
  way to sanity-check the stream without a full GCS.
- Sending a `MAV_CMD_DO_SET_RELAY` command from your GCS's command panel
  (param1 = relay index, e.g. 0; param2 = 1 for on / 0 for off) should
  toggle the onboard LED.

## If you actually need something different

- **Direct point-to-point link to an existing flight controller (Pixhawk,
  ArduPilot, PX4), no GCS relay needed:** skip the Bridge entirely and run
  `pymavlink` on the Linux side against the flight controller's serial/USB
  port directly (`mavutil.mavlink_connection('/dev/ttyUSB0', baud=57600)`),
  then forward with `udpout:<gcs-ip>:14550` if you still want a GCS to see it.
- **MAVLink entirely on the MCU, no Linux involvement:** it's possible to
  vendor the official `mavlink/c_library_v2` headers into the sketch and pack
  messages manually over `Serial1` to a flight controller, the way people do
  on classic Arduino Uno/Nano boards. You lose the networking and easy
  Python tooling, but it removes the MPU from the loop if you want a fully
  standalone real-time node. Say the word if this is actually your use case
  and I'll write that version instead.

## A note on API stability

UNO Q and App Lab are new (2025/2026) and the `Bridge`/`Arduino_RouterBridge`
RPC method names have some churn between releases. If `Bridge.provide(...)`
in the sketch doesn't match what your App Lab version expects, open the
built-in "Bridge" example in App Lab (File > Examples) and match its exact
calling convention — the RPC concept and everything on the Python/MAVLink
side of this bridge will stay the same regardless.
