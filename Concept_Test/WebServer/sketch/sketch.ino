#include "Arduino_RouterBridge.h"

bool ledState = false;

String get_analog(String arg) {
  int value = analogRead(A0);
  return String(value);
}

String get_led(String arg) {
  return ledState ? "OFF" : "ON";
}

String toggle_led(String arg) {
  ledState = !ledState;
  digitalWrite(LED_BUILTIN, ledState ? HIGH : LOW);
  return ledState ? "OFF" : "ON";
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Monitor.begin();
  Bridge.begin();

  Bridge.provide_safe("get_analog", get_analog);
  Bridge.provide_safe("get_led", get_led);
  Bridge.provide_safe("toggle_led", toggle_led);

  Monitor.println("Bridge ready");
}

void loop() {
  // nothing needed here — Bridge calls happen on demand
}
