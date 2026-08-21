#include <WiFi.h>
#include <WiFiUdp.h>

const char* ssid     = "LAPTOP-KH5BNQLP 5885";
const char* password = "987654321";

WiFiUDP udp;
const char* targetIP   = "192.168.137.10";  // UNO Q's IP (Linux side, get via `hostname -I` on the board)
const int   targetPort = 4210;
const int   localPort  = 4211;

unsigned long lastSend = 0;
const unsigned long sendInterval = 1000;
int counter = 0;

void setup() {
  Serial.begin(115200);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  udp.begin(localPort);
}

void loop() {
  if (millis() - lastSend >= sendInterval) {
    lastSend = millis();
    String message = "Hello from ESP32! Count: " + String(counter++);

    udp.beginPacket(targetIP, targetPort);
    udp.print(message);
    udp.endPacket();

    Serial.println("Sent: " + message);
  }
}
