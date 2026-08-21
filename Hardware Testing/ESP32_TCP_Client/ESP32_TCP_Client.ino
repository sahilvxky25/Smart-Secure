/*
  ESP32_TCP_Server.ino
  ----------------------
  Two-way wireless link: ESP32 <--> Arduino UNO Q

  The ESP32 joins your Wi-Fi network and runs a TCP SERVER. The UNO Q
  (via BridgeTCPClient on its STM32 sketch) connects to it as a
  TCP CLIENT.

  This sketch accepts the incoming connection, prints whatever the
  UNO Q sends, and periodically sends a message back.

  Requires: ESP32 board package in Arduino IDE (esp32 by Espressif).
*/

#include <WiFi.h>

// ----------- USER CONFIG -----------
const char* WIFI_SSID     = "OPPO K13 5G 8F3A";
const char* WIFI_PASSWORD = "csgy6924";
const uint16_t SERVER_PORT = 5005;   // must match ESP32_PORT in the UNO Q sketch
// ------------------------------------

WiFiServer server(SERVER_PORT);
WiFiClient client;   // currently-connected UNO Q client

unsigned long lastSend = 0;
const unsigned long SEND_INTERVAL_MS = 2000;
int counter = 0;

void connectWiFi() {
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Connected! ESP32 IP address (use this as ESP32_IP on UNO Q): ");
  Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);
  delay(500);
  connectWiFi();

  server.begin();
  Serial.print("TCP server listening on port ");
  Serial.println(SERVER_PORT);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  // Accept a new client if we don't already have one connected
  if (!client || !client.connected()) {
    WiFiClient newClient = server.available();
    if (newClient) {
      client = newClient;
      Serial.println("UNO Q connected!");
    }
  }

  if (client && client.connected()) {
    // --- RECEIVE: read anything the UNO Q sends ---
    while (client.available()) {
      String line = client.readStringUntil('\n');
      line.trim();
      if (line.length() > 0) {
        Serial.print("Received <- ");
        Serial.println(line);

        // React to commands from the UNO Q here, e.g.:
        // if (line == "CMD:LED_ON") { digitalWrite(LED_PIN, HIGH); }
      }
    }

    // --- SEND: push a message back every 2 seconds ---
    unsigned long now = millis();
    if (now - lastSend >= SEND_INTERVAL_MS) {
      lastSend = now;
      counter++;
      String msg = "ESP32:" + String(counter);
      client.println(msg);
      Serial.print("Sent -> ");
      Serial.println(msg);
    }
  }
}
