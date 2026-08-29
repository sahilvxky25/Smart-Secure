"""
Run this on the ARDUINO UNO Q (Linux/Debian side — via App Lab's Python
component, or directly over SSH/terminal on the board).

SETUP (once, on the UNO Q):
    pip install opencv-python

RUN:
    python3 unoq_camera_client.py

Before running: edit LAPTOP_IP below to match your laptop's WiFi IP
address (from `ipconfig` on the laptop). Both the laptop and the UNO Q
must be connected to the SAME WiFi network.
"""

import cv2

LAPTOP_IP = "192.168.1.42"   # <-- CHANGE THIS to your laptop's IP
STREAM_URL = f"http://{LAPTOP_IP}:5000/video"

cap = cv2.VideoCapture(STREAM_URL)

if not cap.isOpened():
    print(f"Could not open stream at {STREAM_URL}")
    print("Check that: 1) the laptop server is running, "
          "2) both devices are on the same WiFi, "
          "3) the IP address is correct, "
          "4) Windows Firewall isn't blocking port 5000.")
    exit(1)

print("Connected to laptop camera stream. Press Ctrl+C to stop.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Lost connection to stream, retrying...")
        continue

    # --- Do whatever you want with `frame` here ---
    # Examples:
    #   cv2.imshow("Laptop Camera", frame)     # if UNO Q has a display attached
    #   run object detection, save frames, feed into an AI model, etc.

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
