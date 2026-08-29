"""
STEP 2 of face recognition setup — run this on the UNO Q after
enrolling one or more people with face_enroll.py.

Reads all images under dataset/<name>/*.jpg and trains an LBPH
face recognizer model, saving:
    trainer.yml   — the trained model
    labels.json   — mapping of numeric label -> person name

RUN:
    python3 face_train.py
"""

import os
import json
import cv2
import numpy as np

DATASET_DIR = "dataset"
MODEL_PATH = "trainer.yml"
LABELS_PATH = "labels.json"

if not os.path.isdir(DATASET_DIR):
    print(f"No '{DATASET_DIR}/' folder found. Run face_enroll.py first.")
    exit(1)

people = sorted([
    d for d in os.listdir(DATASET_DIR)
    if os.path.isdir(os.path.join(DATASET_DIR, d))
])

if not people:
    print(f"No enrolled people found in '{DATASET_DIR}/'. Run face_enroll.py first.")
    exit(1)

print(f"Found {len(people)} enrolled people: {', '.join(people)}")

label_map = {i: name for i, name in enumerate(people)}
name_to_label = {name: i for i, name in label_map.items()}

faces = []
labels = []

for name in people:
    person_dir = os.path.join(DATASET_DIR, name)
    image_files = [f for f in os.listdir(person_dir) if f.lower().endswith((".jpg", ".png"))]

    if not image_files:
        print(f"Warning: no images found for '{name}', skipping.")
        continue

    for filename in image_files:
        filepath = os.path.join(person_dir, filename)
        img = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        faces.append(img)
        labels.append(name_to_label[name])

    print(f"  {name}: {len(image_files)} images")

if not faces:
    print("No usable images found. Aborting.")
    exit(1)

if not hasattr(cv2, "face"):
    print("ERROR: cv2.face module not found.")
    print("You need 'opencv-contrib-python', not plain 'opencv-python'.")
    print("Fix with:")
    print("    pip uninstall -y opencv-python opencv-python-headless")
    print("    pip install opencv-contrib-python")
    exit(1)

print(f"\nTraining recognizer on {len(faces)} total images...")
recognizer = cv2.face.LBPHFaceRecognizer_create()
recognizer.train(faces, np.array(labels))
recognizer.save(MODEL_PATH)

with open(LABELS_PATH, "w") as f:
    json.dump(label_map, f, indent=2)

print(f"\nDone. Saved model to '{MODEL_PATH}' and labels to '{LABELS_PATH}'.")
print("You can now run the updated unoq_camera_client.py for live recognition.")
