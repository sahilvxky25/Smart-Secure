"""
STEP 3 (final) — Run this on the ARDUINO UNO Q after enrolling people
with face_enroll.py and training the model with face_train.py.

SETUP (once, on the UNO Q):
    pip install opencv-contrib-python
    (must be "opencv-contrib-python" — plain "opencv-python" does NOT
     include cv2.face, which this script needs)

RUN:
    python3 unoq_camera_client.py

Before running: edit LAPTOP_IP below to match your laptop's WiFi IP
address. Both the laptop and the UNO Q must be on the SAME WiFi network.

This detects faces in each frame, matches each one against the people
you enrolled (trainer.yml / labels.json), and prints the recognized
name, confidence, and location to the terminal — no display needed.

If no trainer.yml is found, it falls back to plain face DETECTION
(prints "Unknown" for every face) so you can still test the camera
connection before setting up recognition.
"""

import cv2
import json
import os
import time

LAPTOP_IP = "192.168.137.181"   # <-- CHANGE THIS to your laptop's IP
STREAM_URL = f"http://{LAPTOP_IP}:5000/video"

MODEL_PATH = "trainer.yml"
LABELS_PATH = "labels.json"

# Lower = stricter/more confident match. LBPH "confidence" is actually a
# distance score, so LOWER means MORE similar. Typical good matches are
# under ~60-70; tune this if you get too many false matches or misses.
CONFIDENCE_THRESHOLD = 70

PRINT_INTERVAL = 0.2  # seconds; avoid flooding the terminal every frame

# --- Load face detector (always available in opencv-python) ---
FACE_CASCADE_PATH = "haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)

if face_cascade.empty():
    print(f"Could not load face cascade from {FACE_CASCADE_PATH}")
    exit(1)

# --- Load recognizer + labels, if available ---
recognition_enabled = False
recognizer = None
label_map = {}

if os.path.exists(MODEL_PATH) and os.path.exists(LABELS_PATH):
    if hasattr(cv2, "face"):
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(MODEL_PATH)
        with open(LABELS_PATH) as f:
            raw_map = json.load(f)
        label_map = {int(k): v for k, v in raw_map.items()}
        recognition_enabled = True
        print(f"Loaded recognizer. Known people: {', '.join(label_map.values())}\n")
    else:
        print("Warning: trainer.yml found but cv2.face is unavailable.")
        print("Install 'opencv-contrib-python' to enable recognition.")
        print("Falling back to face DETECTION only (no names).\n")
else:
    print("No trainer.yml/labels.json found — running face DETECTION only.")
    print("Run face_enroll.py then face_train.py to enable recognition.\n")

# --- Connect to the camera stream ---
cap = cv2.VideoCapture(STREAM_URL)

if not cap.isOpened():
    print(f"Could not open stream at {STREAM_URL}")
    print("Check that: 1) the laptop server is running, "
          "2) both devices are on the same WiFi, "
          "3) the IP address is correct, "
          "4) Windows Firewall isn't blocking port 5000.")
    exit(1)

print("Connected to laptop camera stream. Press Ctrl+C to stop.\n")

last_print_time = 0

while True:
    ret, frame = cap.read()
    if not ret:
        print("Lost connection to stream, retrying...")
        continue

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
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
                location_str = (
                    f"x={x}, y={y}, w={w}, h={h}  "
                    f"center=({center_x}, {center_y})  "
                    f"frame_size=({frame_w}x{frame_h})"
                )

                if recognition_enabled:
                    face_roi = cv2.resize(gray[y:y + h, x:x + w], (200, 200))
                    label_id, confidence = recognizer.predict(face_roi)

                    if confidence <= CONFIDENCE_THRESHOLD:
                        name = label_map.get(label_id, "Unknown")
                        print(f"Face {i+1}: {name} (confidence={confidence:.1f})  {location_str}")
                    else:
                        print(f"Face {i+1}: Unknown (confidence={confidence:.1f})  {location_str}")
                else:
                    print(f"Face {i+1}: {location_str}")

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
