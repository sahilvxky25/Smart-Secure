import paho.mqtt.client as mqtt
import time

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_SUB = "myproject/esp32/status"
TOPIC_PUB = "myproject/unoq/command"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code", rc)
    client.subscribe(TOPIC_SUB)

def on_message(client, userdata, msg):
    print(f"{msg.topic}: {msg.payload.decode()}")
    # React to messages from ESP32 here

client = mqtt.Client()
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
