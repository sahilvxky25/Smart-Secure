"""
STEP 1 of face recognition setup — run this on the UNO Q.

Captures sample face photos for one named person from the laptop's
camera stream and saves them to disk. Run this once per person you
want the system to recognize.

SETUP (once, on the UNO Q):
    pip install opencv-contrib-python
    (must be "opencv-contrib-python", not plain "opencv-python" —
     the contrib build includes the face-recognition module)

RUN:
    python3 face_enroll.py "Alice"

Before running: edit LAPTOP_IP below to match your laptop's WiFi IP.

This will open the stream, detect a face, and automatically save
NUM_SAMPLES cropped face images to:
    dataset/<name>/0.jpg, 1.jpg, 2.jpg, ...

Move your head slightly (angle, distance, expression) between shots
for a more robust model. Press 'q' to stop early.
"""

import sys
import os
import time
import cv2

LAPTOP_IP = "192.168.137.181"   # <-- CHANGE THIS to your laptop's IP
STREAM_URL = f"http://{LAPTOP_IP}:5000/video"

NUM_SAMPLES = 30          # how many face images to capture
CAPTURE_INTERVAL = 0.3    # seconds between captures
DATASET_DIR = "dataset"

if len(sys.argv) < 2:
    print("Usage: python3 face_enroll.py \"Person Name\"")
    sys.exit(1)

person_name = sys.argv[1].strip()
save_dir = os.path.join(DATASET_DIR, person_name)
os.makedirs(save_dir, exist_ok=True)

FACE_CASCADE_PATH = "haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)

if face_cascade.empty():
    print(f"Could not load face cascade from {FACE_CASCADE_PATH}")
    sys.exit(1)

cap = cv2.VideoCapture(STREAM_URL)

if not cap.isOpened():
    print(f"Could not open stream at {STREAM_URL}")
    print("Check that: 1) the laptop server is running, "
          "2) both devices are on the same WiFi, "
          "3) the IP address is correct, "
          "4) Windows Firewall isn't blocking port 5000.")
    sys.exit(1)

print(f"Enrolling '{person_name}'. Look at the camera and move your head")
print(f"slightly between captures. Collecting {NUM_SAMPLES} samples...\n")

count = 0
last_capture = 0

while count < NUM_SAMPLES:
    ret, frame = cap.read()
    if not ret:
        print("Lost connection to stream, retrying...")
        continue

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
    )

    now = time.time()
    if len(faces) > 0 and (now - last_capture) >= CAPTURE_INTERVAL:
        # Use the largest detected face (closest / most prominent)
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face_img = gray[y:y + h, x:x + w]
        face_img = cv2.resize(face_img, (200, 200))

        filepath = os.path.join(save_dir, f"{count}.jpg")
        cv2.imwrite(filepath, face_img)
        count += 1
        last_capture = now
        print(f"Captured {count}/{NUM_SAMPLES} -> {filepath}")

    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("Stopped early by user.")
        break

cap.release()
cv2.destroyAllWindows()

print(f"\nDone. Saved {count} images to {save_dir}/")
print("Repeat this script for each additional person, then run face_train.py.")
