"""
MPU (Linux) side of the MAVLink bridge on Arduino UNO Q.

Owns the MAVLink protocol: heartbeats, telemetry messages built from
MCU sensor data (fetched over Bridge), and incoming commands from a
ground control station (QGroundControl, Mission Planner, MAVProxy, ...).

Requires pymavlink on the Linux side:
    pip install pymavlink --break-system-packages

Run inside Arduino App Lab (Python brick) or directly on the board's
Debian shell via `python3 main.py`.
"""

import time
from arduino.app_utils import App, Bridge
from pymavlink import mavutil

# --- MAVLink connection setup ---
# 'udpout' pushes telemetry TO a GCS listening on that host/port.
# QGroundControl listens on UDP 14550 by default.
# If your GCS is on another machine, change 127.0.0.1 to its IP.
MAV_TARGET = "udpout:127.0.0.1:14550"
SYSTEM_ID = 1
COMPONENT_ID = mavutil.mavlink.MAV_COMP_ID_AUTOPILOT1

mav = mavutil.mavlink_connection(
    MAV_TARGET, source_system=SYSTEM_ID, source_component=COMPONENT_ID
)

HEARTBEAT_PERIOD_S = 1.0
_last_heartbeat = 0.0


def send_heartbeat():
    mav.mav.heartbeat_send(
        mavutil.mavlink.MAV_TYPE_GENERIC,
        mavutil.mavlink.MAV_AUTOPILOT_INVALID,
        0,  # base_mode
        0,  # custom_mode
        mavutil.mavlink.MAV_STATE_ACTIVE,
    )


def handle_incoming():
    msg = mav.recv_match(blocking=False)
    if msg is None:
        return

    msg_type = msg.get_type()

    if msg_type == "COMMAND_LONG" and msg.command == mavutil.mavlink.MAV_CMD_DO_SET_RELAY:
        state = bool(int(msg.param2))  # param1 = relay index, param2 = 0/1
        try:
            Bridge.call("set_led", state)
            result = mavutil.mavlink.MAV_RESULT_ACCEPTED
        except Exception as exc:
            print(f"LED command failed: {exc}")
            result = mavutil.mavlink.MAV_RESULT_FAILED

        mav.mav.command_ack_send(msg.command, result)

    elif msg_type == "HEARTBEAT":
        pass  # GCS heartbeat received; extend here for link-loss detection


def loop():
    global _last_heartbeat
    now = time.time()

    if now - _last_heartbeat >= HEARTBEAT_PERIOD_S:
        send_heartbeat()
        _last_heartbeat = now

    handle_incoming()


App.run(user_loop=loop)
