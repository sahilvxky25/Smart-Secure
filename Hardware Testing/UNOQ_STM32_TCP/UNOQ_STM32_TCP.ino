/*
  UNOQ_sketch_only.ino
  ----------------------
  Runs entirely as the "sketch" part of an Arduino App Lab App on the
  UNO Q. The STM32 (MCU) side uses BridgeTCPClient, which tunnels a
  real TCP socket through the Bridge/RPC layer to the Linux (MPU)
  side's Wi-Fi radio. From your code's perspective it behaves like a
  normal WiFiClient/EthernetClient.

  This acts as a TCP CLIENT that connects OUT to the ESP32, which
  runs a TCP SERVER (see the ESP32 sketch below).

  Two-way: sends a counter/status message every second, and prints
  anything the ESP32 sends back.

  Setup in Arduino App Lab:
    1. Create a new App.
    2. Select ALL existing code in sketch/sketch.ino and DELETE it.
    3. Paste this file in.
    4. Leave python/main.py EMPTY — not needed for this approach.
    5. Click Run.
*/

#include "Arduino_RouterBridge.h"

// ----------- USER CONFIG -----------
// IP address the ESP32 gets once it connects to your Wi-Fi network.
// Read it from the ESP32's Serial Monitor after upload.
const char* ESP32_IP = "10.105.47.88";
const uint16_t ESP32_PORT = 5005;
// ------------------------------------

BridgeTCPClient<> client(Bridge);

unsigned long lastSend = 0;
const unsigned long SEND_INTERVAL_MS = 1000;
int counter = 0;
bool wasConnected = false;

void setup() {
  if (!Bridge.begin()) {
    // Bridge failed to start — nothing else will work, halt here.
    while (true) {}
  }

  Serial.begin(9600);
  Serial.println("UNO Q <-> ESP32 TCP link starting...");
}

void loop() {
  // (Re)connect if needed
  if (!client.connected()) {
    if (wasConnected) {
      Serial.println("Disconnected from ESP32. Reconnecting...");
    }
    wasConnected = false;

    Serial.print("Connecting to ESP32 at ");
    Serial.print(ESP32_IP);
    Serial.print(":");
    Serial.println(ESP32_PORT);

    if (client.connect(ESP32_IP, ESP32_PORT) < 0) {
      Serial.println("Connection failed, retrying in 3s...");
      delay(3000);
      return;
    }

    Serial.println("Connected to ESP32!");
    wasConnected = true;
  }

  // --- SEND: push a message every second ---
  unsigned long now = millis();
  if (now - lastSend >= SEND_INTERVAL_MS) {
    lastSend = now;
    counter++;

    // Replace with real sensor data / commands as needed, e.g.:
    // String msg = "CMD:LED_ON";
    String msg = "UNOQ:" + String(counter);

    client.println(msg);
    Serial.print("Sent -> ");
    Serial.println(msg);
  }

  // --- RECEIVE: read anything the ESP32 sends back ---
  String line;
  while (client.connected() && client.available()) {
    char c = client.read();
    if (c == '\n') {
      line.trim();
      if (line.length() > 0) {
        Serial.print("Received <- ");
        Serial.println(line);

        // React to it here, e.g.:
        // if (line == "LED:ON") digitalWrite(LED_BUILTIN, LOW);
      }
      line = "";
    } else if (c != '\r') {
      line += c;
    }
  }
}
