"""
Run this on your WINDOWS LAPTOP.
It shares your webcam over WiFi as an MJPEG stream that the
Arduino UNO Q (or any device on the same network) can read.

SETUP (run once, in Command Prompt or PowerShell):
    pip install flask opencv-python

RUN:
    python laptop_camera_server.py

Then find your laptop's IP with:
    ipconfig
(look for "IPv4 Address" under your active WiFi adapter, e.g. 192.168.1.42)

The stream will be available at:
    http://<your-laptop-ip>:5000/video

NOTE: Windows Firewall may prompt you to allow Python to accept
incoming connections the first time you run this — click "Allow".
"""

import cv2
from flask import Flask, Response

app = Flask(__name__)

# 0 = default webcam. Change to 1, 2, etc. if you have multiple cameras.
CAMERA_INDEX = 0

camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)


def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        ok, buffer = cv2.imencode('.jpg', frame)
        if not ok:
            continue
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


@app.route('/video')
def video():
    return Response(generate_frames(),
                     mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/')
def index():
    return '<h1>Laptop camera stream running</h1><img src="/video" width="640">'


if __name__ == '__main__':
    print("Starting camera server on http://0.0.0.0:5000/video")
    print("Open http://localhost:5000 in a browser on this laptop to test it first.")
    app.run(host='0.0.0.0', port=5000, threaded=True)
