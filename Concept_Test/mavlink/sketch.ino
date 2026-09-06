/*
  MCU (STM32) side of the MAVLink bridge on Arduino UNO Q.
  This sketch does NOT speak MAVLink itself. It just exposes real-time
  sensor readings and actuator control to the Linux/Python side via the
  Bridge RPC library. Python assembles the actual MAVLink messages.

  NOTE: Bridge.provide()/Bridge.begin() call signatures can shift between
  App Lab releases since this is a very new product. Cross-check the
  exact method names against Arduino App Lab's built-in "Bridge" example
  (File > Examples in App Lab) before relying on this in production.
*/

#include <Arduino_RouterBridge.h>

// Uses the board's built-in LED — no external wiring needed.

// --- Functions exposed to the Python (MPU) side ---

// Called from Python when a MAVLink COMMAND_LONG (MAV_CMD_DO_SET_RELAY)
// arrives from the ground station. state: true = on, false = off.
void set_led(bool state) {
  digitalWrite(LED_BUILTIN, state ? HIGH : LOW);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);

  Bridge.begin();
  Bridge.provide("set_led", set_led);
}

void loop() {
  Bridge.update();
  // Add any other time-critical sensor polling / control loops here.
}
