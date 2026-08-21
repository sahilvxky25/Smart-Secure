#include <Arduino_RouterBridge.h>

BridgeUDP<> udp(Bridge);   // <-- template + constructor arg required
const uint16_t localPort = 4210;
uint8_t packetBuffer[255];

void setup() {
  Bridge.begin();
  Monitor.begin(115200);
  while (!Monitor) {}

  udp.begin(localPort);
  Monitor.print("Listening for UDP packets on port ");
  Monitor.println(localPort);
}

void loop() {
  int packetSize = udp.parsePacket();

  if (packetSize > 0) {
    int len = udp.read(packetBuffer, sizeof(packetBuffer) - 1);
    if (len > 0) packetBuffer[len] = '\0';

    IPAddress sender = udp.remoteIP();
    uint16_t senderPort = udp.remotePort();

    Monitor.print("Received from ");
    Monitor.print(sender);
    Monitor.print(":");
    Monitor.print(senderPort);
    Monitor.print(" -> ");
    Monitor.println((char*)packetBuffer);

    udp.beginPacket(sender, senderPort);
    udp.write((const uint8_t*)"ACK", 3);
    udp.endPacket();
  }

  delay(10);
}
