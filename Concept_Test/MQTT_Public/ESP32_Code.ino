#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid = "OPPO K13 5G 8F3A";
const char* password = "csgy6924";

const char* mqtt_server = "broker.hivemq.com"; // free public broker
const int mqtt_port = 1883;
const char* topic_pub = "myproject/esp32/status";
const char* topic_sub = "myproject/unoq/command";

WiFiClient espClient;
PubSubClient client(espClient);

void callback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.print("Received: ");
  Serial.println(msg);
  // React to messages from Uno Q here
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect("ESP32Client-1234")) { // unique client ID
      client.subscribe(topic_sub);
    } else {
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  static unsigned long lastMsg = 0;
  if (millis() - lastMsg > 5000) {
    lastMsg = millis();
    client.publish(topic_pub, "Hello from ESP32!");
  }
}
