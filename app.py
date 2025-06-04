import os
import base64
import sqlite3
import numpy as np
import face_recognition
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, send_file
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Constants
DB_PATH = 'users.db'
UPLOAD_FOLDER = 'uploaded_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -----------------------------
# Database Initialization
# -----------------------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                encoding BLOB NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        conn.commit()

# -----------------------------
# Helper: Face Handling
# -----------------------------
def decode_base64_image(image_data):
    header, encoded = image_data.split(",", 1)
    return base64.b64decode(encoded)

def extract_face_encoding(image_bytes):
    image_stream = BytesIO(image_bytes)
    image = face_recognition.load_image_file(image_stream)
    encodings = face_recognition.face_encodings(image)
    if not encodings:
        return None
    return encodings[0]

def match_face(image_data, threshold=0.45):
    image_bytes = decode_base64_image(image_data)
    unknown_encoding = extract_face_encoding(image_bytes)
    if unknown_encoding is None:
        return "no_face"

    best_match = None
    best_score = float('inf')

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT username, encoding FROM users")
        for username, encoding_blob in c.fetchall():
            known_encoding = np.frombuffer(encoding_blob, dtype=np.float64)
            distance = face_recognition.face_distance([known_encoding], unknown_encoding)[0]

            if distance < threshold and distance < best_score:
                best_score = distance
                best_match = username

    return best_match  # Can be None if no good match

# -----------------------------
# Routes
# -----------------------------
@app.route('/')
def home():
    return redirect('/login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        image_data = request.form['face_image']
        image_bytes = decode_base64_image(image_data)
        encoding = extract_face_encoding(image_bytes)

        if encoding is None:
            flash("No face detected. Make sure your face is clearly visible.", "danger")
            return redirect('/register')

        encoding_blob = encoding.tobytes()
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute('INSERT INTO users (username, encoding) VALUES (?, ?)', (username, encoding_blob))
                conn.commit()
                flash("Registration successful!", "success")
                return redirect('/login')
        except sqlite3.IntegrityError:
            flash("Username already exists.", "warning")
            return redirect('/register')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        image_data = request.form['face_image']
        image_bytes = decode_base64_image(image_data)
        encoding = extract_face_encoding(image_bytes)

        if encoding is None:
            flash("No face detected. Please try again with a clearer image.", "warning")
            return redirect('/login')

        user = match_face(image_data)
        if user == "no_face":
            flash("No face detected. Try again.", "danger")
            return redirect('/login')
        elif user:
            flash(f"Welcome {user}!", "success")
            return redirect(url_for('dashboard', username=user))
        else:
            flash("Face not recognized. Please try again or register.", "danger")
            return redirect('/login')

    return render_template('login.html')

@app.route('/dashboard/<username>')
def dashboard(username):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT id, file_name, file_path, upload_time FROM files WHERE username=?', (username,))
        files = c.fetchall()
    return render_template('dashboard.html', username=username, files=files)

@app.route('/upload', methods=['POST'])
def upload_file():
    username = request.form['username']
    uploaded_file = request.files['file']
    if uploaded_file.filename != '':
        filename = f"{username}{int(np.random.rand() * 100000)}{uploaded_file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        uploaded_file.save(filepath)

        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('INSERT INTO files (username, file_name, file_path) VALUES (?, ?, ?)',
                      (username, uploaded_file.filename, filepath))
            conn.commit()

        flash("✅ File uploaded successfully!", "success")
    else:
        flash("⚠ No file selected.", "warning")
    return redirect(url_for('dashboard', username=username))

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory(UPLOAD_FOLDER, os.path.basename(filename), as_attachment=True)

@app.route('/preview/<path:filename>')
def preview_file(filename):
    file_path = os.path.join(UPLOAD_FOLDER, os.path.basename(filename))
    if not os.path.isfile(file_path):
        return "File not found", 404
    return send_file(file_path)

@app.route('/delete/<int:file_id>/<username>', methods=['POST'])
def delete_file(file_id, username):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT file_path FROM files WHERE id=? AND username=?', (file_id, username))
        file = c.fetchone()
        if file:
            try:
                os.remove(file[0])
            except FileNotFoundError:
                pass
            c.execute('DELETE FROM files WHERE id=? AND username=?', (file_id, username))
            conn.commit()
            flash("🗑 File deleted successfully.", "success")
        else:
            flash("❌ File not found or access denied.", "danger")
    return redirect(url_for('dashboard', username=username))


@app.route('/contact', methods=['GET', 'POST'])
def contact():
      return render_template('contact.html')

# -----------------------------
# Start the App
# -----------------------------
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
