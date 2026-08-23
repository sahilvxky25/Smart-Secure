import paho.mqtt.client as mqtt
import ssl
import time

MQTT_BROKER = "ce3bdf354139496db2398375c779fa5c.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "unoq_esp32"
MQTT_PASS = "Smart@123"

TOPIC_SUB = "myproject/esp32/status"
TOPIC_PUB = "myproject/unoq/command"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code", rc)
    client.subscribe(TOPIC_SUB)

def on_message(client, userdata, msg):
    print(f"{msg.topic}: {msg.payload.decode()}")

client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

try:
    while True:
        client.publish(TOPIC_PUB, "Hello from Uno Q!")
        time.sleep(5)
except KeyboardInterrupt:
    client.loop_stop()
