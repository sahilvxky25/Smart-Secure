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

This version detects faces in each frame using OpenCV's built-in Haar
Cascade face detector and prints the face location (x, y, width, height,
and center point) to the terminal — no display/monitor needed on the UNO Q.
"""

import cv2
import time

LAPTOP_IP = "192.168.137.181"   # <-- CHANGE THIS to your laptop's IP
STREAM_URL = f"http://{LAPTOP_IP}:5000/video"

# Load OpenCV's built-in pretrained face detector (ships with opencv-python,
# no extra download needed).
FACE_CASCADE_PATH = "haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)

if face_cascade.empty():
    print(f"Could not load face cascade from {FACE_CASCADE_PATH}")
    exit(1)

cap = cv2.VideoCapture(STREAM_URL)

if not cap.isOpened():
    print(f"Could not open stream at {STREAM_URL}")
    print("Check that: 1) the laptop server is running, "
          "2) both devices are on the same WiFi, "
          "3) the IP address is correct, "
          "4) Windows Firewall isn't blocking port 5000.")
    exit(1)

print("Connected to laptop camera stream. Press Ctrl+C to stop.")
print("Watching for faces... (location will be printed below)\n")

last_print_time = 0
PRINT_INTERVAL = 0.2  # seconds; avoid flooding the terminal every frame

while True:
    ret, frame = cap.read()
    if not ret:
        print("Lost connection to stream, retrying...")
        continue

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30)
    )

    now = time.time()
    if now - last_print_time >= PRINT_INTERVAL:
        last_print_time = now
        frame_h, frame_w = frame.shape[:2]

        if len(faces) == 0:
            print("No face detected", end="\r")
        else:
            for i, (x, y, w, h) in enumerate(faces):
                center_x = x + w // 2
                center_y = y + h // 2
                print(
                    f"Face {i+1}: x={x}, y={y}, w={w}, h={h}  "
                    f"center=({center_x}, {center_y})  "
                    f"frame_size=({frame_w}x{frame_h})"
                )

    # --- Do whatever else you want with `frame` / `faces` here ---
    # Example (only if a display is attached to the UNO Q):
    #   for (x, y, w, h) in faces:
    #       cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    #   cv2.imshow("Laptop Camera", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()