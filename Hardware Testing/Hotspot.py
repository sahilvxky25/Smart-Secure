from flask import Flask, jsonify
import random
import time

app = Flask(__name__)

@app.route('/data', methods=['GET'])
def send_data():
    # In a full project, you would read real sensor data from the STM32 MCU
    # Here, we simulate a temperature sensor reading.
    sensor_data = {
        "status": "success",
        "timestamp": time.time(),
        "temperature_c": round(random.uniform(22.0, 26.0), 2),
        "message": "Data sent directly from the UNO Q Hotspot!"
    }
    
    print("Data requested by client.")
    return jsonify(sensor_data)

if __name__ == '__main__':
    # host='0.0.0.0' ensures the server listens on all interfaces, including the hotspot (wlan0)
    # port=8080 is standard for local API testing
    print("Starting UNO Q Data Server...")
    app.run(host='0.0.0.0', port=8080)