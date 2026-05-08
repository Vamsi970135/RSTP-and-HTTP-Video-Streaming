import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
import face_recognition
import os
import cv2
import pickle

# ------------------ SETUP ------------------

KNOWN_FACES_DIR = "known_faces"
ENCODINGS_FILE = "encodings.pkl"

# Auto-create folder
if not os.path.exists(KNOWN_FACES_DIR):
    os.makedirs(KNOWN_FACES_DIR)

known_encodings = []
known_names = []

# ------------------ LOAD ENCODINGS ------------------

def load_encodings():
    global known_encodings, known_names

    if os.path.exists(ENCODINGS_FILE):
        with open(ENCODINGS_FILE, "rb") as f:
            data = pickle.load(f)
            known_encodings = data["encodings"]
            known_names = data["names"]
    else:
        known_encodings = []
        known_names = []

# ------------------ SAVE ENCODINGS ------------------

def save_encodings():
    with open(ENCODINGS_FILE, "wb") as f:
        pickle.dump({
            "encodings": known_encodings,
            "names": known_names
        }, f)

# ------------------ GUI ------------------

root = tk.Tk()
root.title("Face Recognition App (Single File)")
root.geometry("500x600")
root.configure(bg="#f0f0f0")

title = tk.Label(root, text="Face Recognition System", font=("Arial", 18, "bold"), bg="#f0f0f0")
title.pack(pady=10)

image_label = tk.Label(root, bg="#ddd")
image_label.pack(pady=10)

result_label = tk.Label(root, text="", font=("Arial", 16), bg="#f0f0f0")
result_label.pack(pady=10)

current_image_path = None

load_encodings()

# ------------------ FUNCTIONS ------------------

def upload_image():
    global current_image_path

    path = filedialog.askopenfilename(filetypes=[("Image Files", "*.jpg *.png *.jpeg")])
    if not path:
        return

    current_image_path = path

    img = Image.open(path)
    img = img.resize((300, 300))
    img = ImageTk.PhotoImage(img)

    image_label.config(image=img)
    image_label.image = img

    result_label.config(text="Image Loaded")

def check_face():
    if not current_image_path:
        messagebox.showerror("Error", "Upload image first")
        return

    image = face_recognition.load_image_file(current_image_path)
    encodings = face_recognition.face_encodings(image)

    if not encodings:
        result_label.config(text="No Face Detected ❌")
        return

    face_encoding = encodings[0]

    if len(known_encodings) == 0:
        result_label.config(text="No Faces Enrolled ❗")
        return

    matches = face_recognition.compare_faces(known_encodings, face_encoding)
    face_distances = face_recognition.face_distance(known_encodings, face_encoding)

    best_match_index = None

    if True in matches:
        best_match_index = matches.index(True)

    if best_match_index is not None:
        name = known_names[best_match_index]
        confidence = (1 - face_distances[best_match_index]) * 100
        result_label.config(text=f"YES ✅ ({name})\nConfidence: {confidence:.2f}%")
    else:
        result_label.config(text="NO ❌ (Unknown)")

def enroll_face():
    global current_image_path

    if not current_image_path:
        messagebox.showerror("Error", "Upload image first")
        return

    name = simpledialog.askstring("Input", "Enter person name:")

    if not name:
        return

    image = face_recognition.load_image_file(current_image_path)
    encodings = face_recognition.face_encodings(image)

    if not encodings:
        messagebox.showerror("Error", "No face detected")
        return

    face_encoding = encodings[0]

    # Save image
    save_path = os.path.join(KNOWN_FACES_DIR, f"{name}.jpg")
    img = cv2.imread(current_image_path)
    cv2.imwrite(save_path, img)

    # Save encoding
    known_encodings.append(face_encoding)
    known_names.append(name)
    save_encodings()

    messagebox.showinfo("Success", f"{name} enrolled successfully ✅")

# ------------------ BUTTONS ------------------

btn_style = {"width": 20, "height": 2, "font": ("Arial", 12)}

tk.Button(root, text="Upload Image", command=upload_image, **btn_style).pack(pady=10)
tk.Button(root, text="Check Face", command=check_face, **btn_style).pack(pady=10)
tk.Button(root, text="Enroll Face", command=enroll_face, **btn_style).pack(pady=10)

# ------------------ RUN ------------------

root.mainloop()