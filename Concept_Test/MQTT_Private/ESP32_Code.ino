#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>

const char* ssid = "OPPO K13 5G 8F3A";
const char* password = "csgy6924";

const char* mqtt_server = "ce3bdf354139496db2398375c779fa5c.s1.eu.hivemq.cloud";
const int mqtt_port = 8883;
const char* mqtt_user = "unoq_esp32";
const char* mqtt_pass = "Smart@123";

const char* topic_pub = "myproject/esp32/status";
const char* topic_sub = "myproject/unoq/command";

WiFiClientSecure espClient;
PubSubClient client(espClient);

void callback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.print("Received on ");
  Serial.print(topic);
  Serial.print(": ");
  Serial.println(msg);
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Connecting to MQTT...");
    if (client.connect("ESP32Client-1234", mqtt_user, mqtt_pass)) {
      Serial.println("connected");
      client.subscribe(topic_sub);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" retrying in 3s");
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");
  Serial.print("Local IP: ");
  Serial.println(WiFi.localIP());

  espClient.setInsecure(); // HiveMQ Cloud uses standard public CAs
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  static unsigned long lastMsg = 0;
  if (millis() - lastMsg > 5000) {
    lastMsg = millis();
    String payload = "Hello from ESP32! Uptime: " + String(millis() / 1000) + "s";
    client.publish(topic_pub, payload.c_str());
    Serial.println("Published: " + payload);
  }
}
