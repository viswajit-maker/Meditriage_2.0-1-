from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_talisman import Talisman
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.hybrid import hybrid_property
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet, InvalidToken
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from PIL import Image as PilImage
from PIL import UnidentifiedImageError
import magic
import requests as http_requests
import csv
import io
import json
import os
import pickle
import base64
import threading
import time
import uuid
import numpy as np
import pandas as pd
import joblib
from collections import defaultdict, deque
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ── Transport Security ──────────────────────────────────────────────────────
# force_https is only enabled in production (behind a TLS-terminating proxy).
# In local dev (PRODUCTION != 'true') Talisman still adds the security
# response headers but never redirects plain-HTTP requests.
_in_production = os.environ.get('PRODUCTION', 'false').lower() == 'true'
Talisman(
    app,
    force_https=_in_production,
    force_https_permanent=_in_production,          # 301 rather than 302
    strict_transport_security=_in_production,       # HSTS header
    strict_transport_security_max_age=31536000,     # 1 year
    strict_transport_security_include_subdomains=True,
    strict_transport_security_preload=True,
    content_security_policy=False,                  # CSP managed separately
    referrer_policy='strict-origin-when-cross-origin',
    feature_policy={
        'camera': '\'self\'',                       # allow only same-origin camera
        'microphone': '\'self\'',
        'geolocation': '\'none\'',
    },
)

# ── Database ──────────────────────────────────────────────────────
DB_PATH = Path(__file__).with_name('meditriage.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ── Authentication ──────────────────────────────────────────────────
jwt_secret = os.environ.get('JWT_SECRET_KEY', '').strip()
if not jwt_secret:
    raise RuntimeError("JWT_SECRET_KEY is not set. Add it to backend/.env and restart.")
app.config['JWT_SECRET_KEY'] = jwt_secret
jwt = JWTManager(app)

# ── User Model ────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='patient') # patient, doctor, hospital_booking, admin



# ── PatientImage Model ────────────────────────────────────────────────
class PatientImage(db.Model):
    """Stores only the UUID key and metadata — never a raw file path."""
    __tablename__ = 'patient_images'

    id             = db.Column(db.String(36), primary_key=True,
                               default=lambda: str(uuid.uuid4()))
    patient_id     = db.Column(db.String(255), nullable=False, index=True)
    uploaded_at    = db.Column(db.DateTime(timezone=True), nullable=False,
                               default=lambda: datetime.now(timezone.utc))
    retention_hold = db.Column(db.Boolean, nullable=False, default=False)
    # image_id (== id) IS the storage key; no raw path is ever persisted
# ── Image encryption helpers ─────────────────────────────────────────────
IMAGE_STORE     = Path(__file__).with_name('image_store')
IMAGE_STORE.mkdir(exist_ok=True)

MAX_IMAGE_BYTES   = 8 * 1024 * 1024          # 8 MB hard limit
ALLOWED_MIMES     = {'image/jpeg', 'image/png'}
MIME_TO_PIL_FMT   = {'image/jpeg': 'JPEG', 'image/png': 'PNG'}
MIME_TO_CONTENT   = {'image/jpeg': 'image/jpeg', 'image/png': 'image/png'}


def _image_cipher() -> Fernet:
    """Return a Fernet instance using the IMAGE_ENC_KEY env var.
    Raises RuntimeError if the key is absent — never falls back to a default."""
    key = os.environ.get('IMAGE_ENC_KEY', '').strip()
    if not key:
        raise RuntimeError(
            'IMAGE_ENC_KEY is not set. Add it to backend/.env and restart.'
        )
    try:
        return Fernet(key.encode())
    except Exception:
        raise RuntimeError('IMAGE_ENC_KEY is not a valid Fernet key.')


def _field_cipher() -> Fernet:
    """Return a Fernet instance using the FIELD_ENC_KEY env var."""
    key = os.environ.get('FIELD_ENC_KEY', '').strip()
    if not key:
        raise RuntimeError(
            'FIELD_ENC_KEY is not set. Add it to backend/.env and restart.'
        )
    try:
        return Fernet(key.encode())
    except Exception:
        raise RuntimeError('FIELD_ENC_KEY is not a valid Fernet key.')


# ── Patient Model (Encrypted Fields) ─────────────────────────────────────
class Patient(db.Model):
    __tablename__ = 'patients'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assigned_doctor_id = db.Column(db.String(36), nullable=True) # for ownership check
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Encrypted columns stored as bytes
    _name_enc = db.Column("name_enc", db.LargeBinary, nullable=False)
    _phone_enc = db.Column("phone_enc", db.LargeBinary, nullable=True)
    _symptoms_enc = db.Column("symptoms_enc", db.LargeBinary, nullable=False)

    @property
    def name(self):
        return _field_cipher().decrypt(self._name_enc).decode('utf-8') if self._name_enc else None

    @name.setter
    def name(self, value):
        self._name_enc = _field_cipher().encrypt(value.encode('utf-8')) if value else None

    @property
    def phone(self):
        return _field_cipher().decrypt(self._phone_enc).decode('utf-8') if self._phone_enc else None

    @phone.setter
    def phone(self, value):
        self._phone_enc = _field_cipher().encrypt(value.encode('utf-8')) if value else None

    @property
    def symptoms(self):
        return _field_cipher().decrypt(self._symptoms_enc).decode('utf-8') if self._symptoms_enc else None

    @symptoms.setter
    def symptoms(self, value):
        self._symptoms_enc = _field_cipher().encrypt(value.encode('utf-8')) if value else None


# ── Consent Model ────────────────────────────────────────────────────────
class Consent(db.Model):
    __tablename__ = 'consents'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id = db.Column(db.String(255), nullable=False, index=True)
    purpose = db.Column(db.String(255), nullable=False)
    consent_version = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


# ── AccessLog Model ──────────────────────────────────────────────────────
class AccessLog(db.Model):
    __tablename__ = 'access_logs'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_id = db.Column(db.String(36), nullable=False, index=True)
    resource_type = db.Column(db.String(50), nullable=False) # 'patient' or 'image'
    resource_id = db.Column(db.String(36), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False) # 'read', 'delete', etc.
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


def log_access(actor_id: str, resource_type: str, resource_id: str, action: str):
    """Helper to record an audit log asynchronously/synchronously."""
    try:
        log_entry = AccessLog(
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        # Don't fail the request if logging fails, but do log to stderr
        print(f"Failed to write audit log: {e}")



# Ensure tables exist at startup
with app.app_context():
    db.create_all()


MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_AUDIO_DURATION_MS = 30_000
MAX_VOICE_REQUESTS = 5
VOICE_WINDOW_SECONDS = 5 * 60
VOICE_REQUESTS = defaultdict(deque)
VOICE_LOCK = threading.Lock()
LANGUAGE_HINTS = {
    "en": "English", "hi": "Hindi", "ta": "Tamil", "te": "Telugu", "kn": "Kannada",
}


def load_local_environment():
    """Load the ignored local .env file without adding a runtime dependency."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_environment()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# The supplied model was trained to map a disease label to its first recorded
# precaution.  Its encoders were not included, so their deterministic label
# order is rebuilt from the accompanying training CSV at startup.
TRAINED_MODEL_DIR = Path(
    os.environ.get("MEDITRIAGE_MODEL_DIR", Path(__file__).resolve().parents[2] / "trained_model")
)
NO_PRECAUTION = "NO_PRECAUTION_RECORDED"


def load_disease_model():
    """Load the real symptoms->disease classifier and its supporting artifacts."""
    model_path = "C:\\Users\\viswajit\\Downloads\\Meditriage_2.0-main (1)\\disease_model.pkl"
    columns_path = "C:\\Users\\viswajit\\Downloads\\Meditriage_2.0-main (1)\\feature_columns.pkl"
    precautions_path ="C:\\Users\\viswajit\\Downloads\\Meditriage_2.0-main (1)\\precautions.json"

    missing = [p.name for p in (model_path, columns_path, precautions_path) if not os.path.exists(p)]
    if missing:
        raise RuntimeError(
            f"Trained-model files are missing from {TRAINED_MODEL_DIR}: {', '.join(missing)}. "
            "Expected disease_model.pkl, feature_columns.pkl, and precautions.json."
        )

    model = joblib.load(model_path)
    feature_columns = joblib.load(columns_path)

    with Path(precautions_path).open("r", encoding="utf-8") as precautions_file:
        precautions = json.load(precautions_file)

    return model, feature_columns, precautions


DISEASE_MODEL, FEATURE_COLUMNS, PRECAUTIONS_BY_DISEASE = load_disease_model()

# The 28 symptom names the model was trained on, in the exact spelling it expects.
# (Everything in FEATURE_COLUMNS that isn't 'Age' or a 'Gender_*' dummy column.)
KNOWN_SYMPTOMS = [c for c in FEATURE_COLUMNS if c not in ("Age", "Gender_Female", "Gender_Male", "Gender_Other")]


def build_feature_row(age, gender, symptom_list):
    """Build a single-row DataFrame matching FEATURE_COLUMNS exactly, in order."""
    row = {col: 0 for col in FEATURE_COLUMNS}
    row["Age"] = age
    gender_col = f"Gender_{gender}"
    if gender_col in row:
        row[gender_col] = 1
    matched = []
    for sym in symptom_list:
        if sym in row:  # only real trained symptom columns can be set
            row[sym] = 1
            matched.append(sym)
    return pd.DataFrame([row], columns=FEATURE_COLUMNS), matched


def predict_diseases(age, gender, symptom_list, top_k=3):
    """Run the REAL trained model and return the top-k (disease, confidence) predictions."""
    X_row, matched = build_feature_row(age, gender, symptom_list)
    proba = DISEASE_MODEL.predict_proba(X_row)[0]
    classes = DISEASE_MODEL.classes_
    top_idx = np.argsort(proba)[::-1][:top_k]
    top_predictions = [(classes[i], float(proba[i])) for i in top_idx]
    return top_predictions, matched


def recommended_precautions_for(disease):
    return list(PRECAUTIONS_BY_DISEASE.get(disease, []))


def voice_rate_limit_exceeded(client_ip):
    now = time.monotonic()
    with VOICE_LOCK:
        requests_for_ip = VOICE_REQUESTS[client_ip]
        while requests_for_ip and now - requests_for_ip[0] > VOICE_WINDOW_SECONDS:
            requests_for_ip.popleft()
        if len(requests_for_ip) >= MAX_VOICE_REQUESTS:
            return True
        requests_for_ip.append(now)
    return False


@app.route('/voice-symptoms', methods=['POST'])
def voice_symptoms():
    """Translate a short in-memory browser recording into editable English symptoms."""
    client_ip = request.remote_addr or "unknown"
    if voice_rate_limit_exceeded(client_ip):
        return jsonify({"error": "Too many voice requests. Please wait a few minutes and try again."}), 429

    if not GEMINI_API_KEY:
        return jsonify({"error": "Voice transcription is not configured. Add GEMINI_API_KEY to backend/.env."}), 503

    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "No speech detected, please try again."}), 400

    try:
        duration_ms = int(request.form.get("duration_ms", "0"))
    except ValueError:
        duration_ms = 0
    if duration_ms < 500:
        return jsonify({"error": "No speech detected, please try again."}), 400
    if duration_ms > MAX_AUDIO_DURATION_MS:
        return jsonify({"error": "Recording is too long. Please keep it under 30 seconds."}), 400

    audio_bytes = audio_file.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) < 1_000:
        return jsonify({"error": "No speech detected, please try again."}), 400
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return jsonify({"error": "Recording is too large. Please try a shorter recording."}), 413

    language_code = request.form.get("language_hint", "").strip().lower()
    language_hint = LANGUAGE_HINTS.get(language_code, "auto-detect the language")
    mime_type = audio_file.mimetype or "audio/webm"
    prompt = (
        "You are a medical intake transcription assistant. The patient may speak in "
        f"{language_hint}. Listen to the audio, transcribe it, and translate the symptom "
        "description into clear, plain English. Return ONLY the translated English symptom text. "
        "Do not diagnose, add advice, use headings, or add text outside the translation. "
        "If there is no intelligible human speech, return exactly: NO_SPEECH_DETECTED"
    )
    payload = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(audio_bytes).decode("ascii")}},
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 128},
    }

    try:
        response = http_requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent",
            params={"key": GEMINI_API_KEY}, json=payload, timeout=30,
        )
    except http_requests.Timeout:
        return jsonify({"error": "Voice transcription timed out. Please try again."}), 504
    except http_requests.RequestException:
        return jsonify({"error": "Could not reach the voice transcription service. Please check your connection and try again."}), 502

    if response.status_code != 200:
        return jsonify({"error": "Voice transcription service could not process this recording. Please try again."}), 502

    try:
        result = response.json()
        symptoms_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, ValueError):
        return jsonify({"error": "Voice transcription returned an unreadable response. Please try again."}), 502

    if not symptoms_text or symptoms_text.upper() == "NO_SPEECH_DETECTED":
        return jsonify({"error": "No speech detected, please try again."}), 422
    return jsonify({"symptoms_text": symptoms_text})

# ─────────────────────────────────────────────────────────────
# DISEASE + SYMPTOM DATA
# Source: Healthcare.csv (25000 patients, 30 diseases, 28 symptoms)
# Diseases: Allergy, Anemia, Anxiety, Arthritis, Asthma,
#   Bronchitis, COVID-19, Chronic Kidney Disease, Common Cold,
#   Dementia, Depression, Dermatitis, Diabetes, Epilepsy,
#   Food Poisoning, Gastritis, Heart Disease, Hypertension,
#   IBS, Influenza, Liver Disease, Migraine, Obesity,
#   Parkinson's, Pneumonia, Sinusitis, Stroke, Thyroid Disorder,
#   Tuberculosis, Ulcer
# Symptoms: abdominal pain, anxiety, appetite loss, back pain,
#   blurred vision, chest pain, cough, depression, diarrhea,
#   dizziness, fatigue, fever, headache, insomnia, joint pain,
#   muscle pain, nausea, rash, runny nose, shortness of breath,
#   sneezing, sore throat, sweating, swelling, tremors,
#   vomiting, weight gain, weight loss
#
# NOTE: The CSV symptom-disease distribution is statistically
# uniform (each symptom appears ~18% per disease regardless of
# disease type). Clinical weights below are derived from real
# medical literature, not from CSV frequencies.
# ─────────────────────────────────────────────────────────────

DISEASES = {
    "Allergy": {
        "symptoms": {"sneezing":10,"runny nose":9,"rash":8,"cough":5,
                     "headache":4,"fatigue":4,"sore throat":3,"swelling":4,
                     "watery eyes":6},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "Allergist / ENT Specialist",
        "advice": "Identify and avoid allergen triggers. Antihistamines can relieve symptoms."
    },
    "Anemia": {
        "symptoms": {"fatigue":9,"dizziness":8,"headache":7,
                     "shortness of breath":7,"blurred vision":6,
                     "nausea":4,"appetite loss":4,"insomnia":3},
        "age_fn": lambda a: 1.2 if a < 18 or a > 60 else 1.0,
        "risk": "Medium",
        "specialist": "Hematologist",
        "advice": "Get a CBC blood test. Increase iron-rich foods: spinach, lentils, red meat."
    },
    "Anxiety": {
        "symptoms": {"anxiety":10,"insomnia":8,"fatigue":6,"headache":5,
                     "dizziness":5,"chest pain":4,"nausea":4,
                     "tremors":4,"sweating":4,"shortness of breath":4},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "Psychiatrist / Psychologist",
        "advice": "Practice deep breathing and mindfulness. Consider professional counselling."
    },
    "Arthritis": {
        "symptoms": {"joint pain":10,"muscle pain":8,"swelling":7,
                     "fatigue":5,"back pain":6,"dizziness":2,
                     "depression":2,"insomnia":3},
        "age_fn": lambda a: 1.8 if a > 55 else 1.0,
        "risk": "Low",
        "specialist": "Rheumatologist",
        "advice": "Gentle exercise like swimming or walking helps. Avoid high-impact activity."
    },
    "Asthma": {
        "symptoms": {"shortness of breath":10,"cough":9,"chest pain":7,
                     "fatigue":5,"anxiety":5,"sweating":3,"dizziness":3},
        "age_fn": lambda a: 1.0,
        "risk": "Medium",
        "specialist": "Pulmonologist",
        "advice": "Use prescribed inhaler. Avoid dust, smoke, and cold air triggers."
    },
    "Bronchitis": {
        "symptoms": {"cough":10,"chest pain":8,"shortness of breath":7,
                     "fatigue":6,"fever":5,"sore throat":5,
                     "sweating":3,"headache":3,"muscle pain":3},
        "age_fn": lambda a: 1.0,
        "risk": "Medium",
        "specialist": "Pulmonologist",
        "advice": "Rest and stay hydrated. Use a humidifier. See a doctor if fever persists."
    },
    "COVID-19": {
        "symptoms": {"fever":9,"cough":9,"fatigue":8,"shortness of breath":8,
                     "headache":6,"sore throat":6,"diarrhea":5,
                     "vomiting":4,"muscle pain":5,"nausea":4},
        "age_fn": lambda a: 1.5 if a > 60 else 1.0,
        "risk": "Medium",
        "specialist": "General Physician",
        "advice": "Isolate immediately. Monitor oxygen saturation. Seek care if SpO2 < 94%."
    },
    "Chronic Kidney Disease": {
        "symptoms": {"swelling":10,"fatigue":9,"appetite loss":8,
                     "nausea":7,"blurred vision":6,"headache":5,
                     "dizziness":5,"weight loss":4,"vomiting":5},
        "age_fn": lambda a: 1.6 if a > 50 else 1.0,
        "risk": "High",
        "specialist": "Nephrologist",
        "advice": "See a nephrologist urgently. Reduce protein and sodium in your diet."
    },
    "Common Cold": {
        "symptoms": {"runny nose":10,"sore throat":9,"sneezing":8,
                     "cough":7,"headache":5,"fever":4,
                     "fatigue":4,"muscle pain":3},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "General Physician",
        "advice": "Rest, drink warm fluids, use saline nasal spray. Should resolve in 7 days."
    },
    "Dementia": {
        "symptoms": {"depression":8,"insomnia":8,"anxiety":7,
                     "fatigue":5,"dizziness":4,"headache":4,
                     "weight loss":4,"appetite loss":4},
        "age_fn": lambda a: 4.0 if a > 75 else (2.0 if a > 65 else 0.2),
        "risk": "High",
        "specialist": "Neurologist / Geriatrician",
        "advice": "Seek geriatric neurology evaluation. Cognitive assessment is needed urgently."
    },
    "Depression": {
        "symptoms": {"depression":10,"insomnia":9,"fatigue":8,
                     "appetite loss":7,"anxiety":6,"headache":4,
                     "weight loss":4,"weight gain":3,"dizziness":3},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "Psychiatrist",
        "advice": "Please speak to someone you trust. Professional help makes a real difference."
    },
    "Depression": {
        "symptoms": {"depression":10,"insomnia":9,"fatigue":8,
                     "appetite loss":7,"anxiety":6,"headache":4,
                     "weight loss":4,"weight gain":3,"dizziness":3},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "Psychiatrist",
        "advice": "Please speak to someone you trust. Professional help makes a real difference."
    },
    "Dermatitis": {
        "symptoms": {"rash":10,"swelling":7,"anxiety":4,
                     "fatigue":3,"headache":3,"nausea":2},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "Dermatologist",
        "advice": "Avoid scratching. Apply moisturizer. See a dermatologist for prescription cream."
    },
    "Diabetes": {
        "symptoms": {"fatigue":9,"blurred vision":9,"weight loss":8,
                     "nausea":5,"dizziness":5,"headache":4,
                     "sweating":5,"appetite loss":3,"vomiting":3},
        "age_fn": lambda a: 1.5 if a > 40 else 1.0,
        "risk": "Medium",
        "specialist": "Endocrinologist",
        "advice": "Check fasting blood sugar. Follow a low-sugar, high-fibre diet."
    },
    "Epilepsy": {
        "symptoms": {"tremors":10,"dizziness":8,"headache":6,
                     "anxiety":6,"fatigue":5,"nausea":4,
                     "blurred vision":5,"muscle pain":3},
        "age_fn": lambda a: 1.0,
        "risk": "High",
        "specialist": "Neurologist",
        "advice": "Do not drive. Get an EEG done. Take prescribed anticonvulsants regularly."
    },
    "Food Poisoning": {
        "symptoms": {"vomiting":10,"diarrhea":10,"nausea":9,
                     "abdominal pain":8,"fever":5,"headache":4,
                     "fatigue":4,"muscle pain":3},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "General Physician",
        "advice": "Drink ORS regularly. Avoid solid food for a few hours. Rest completely."
    },
    "Gastritis": {
        "symptoms": {"nausea":9,"vomiting":8,"abdominal pain":9,
                     "headache":5,"appetite loss":6,"fatigue":4,
                     "sweating":3,"dizziness":3},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "Gastroenterologist",
        "advice": "Eat smaller meals. Avoid spicy and acidic food. Take antacids after meals."
    },
    "Heart Disease": {
        "symptoms": {"chest pain":10,"shortness of breath":9,"sweating":8,
                     "fatigue":7,"nausea":5,"dizziness":5,
                     "swelling":5,"anxiety":3,"back pain":2},
        "age_fn": lambda a: 1.9 if a > 55 else (1.3 if a > 40 else 1.0),
        "risk": "High",
        "specialist": "Cardiologist",
        "advice": "Seek emergency care immediately. Avoid any physical exertion."
    },
    "Hypertension": {
        "symptoms": {"headache":9,"dizziness":8,"shortness of breath":7,
                     "chest pain":6,"fatigue":5,"nausea":4,
                     "blurred vision":5,"anxiety":4,"sweating":3},
        "age_fn": lambda a: 1.6 if a > 50 else (1.2 if a > 35 else 1.0),
        "risk": "Medium",
        "specialist": "Cardiologist",
        "advice": "Monitor BP daily. Reduce salt and stress. Regular exercise is essential."
    },
    "IBS": {
        "symptoms": {"abdominal pain":10,"diarrhea":9,"nausea":7,
                     "vomiting":5,"anxiety":6,"fatigue":5,
                     "appetite loss":4,"headache":3},
        "age_fn": lambda a: 1.0,
        "risk": "Medium",
        "specialist": "Gastroenterologist",
        "advice": "Follow a low-FODMAP diet. Stress management significantly reduces IBS flares."
    },
    "Influenza": {
        "symptoms": {"fever":9,"muscle pain":9,"fatigue":8,
                     "headache":7,"sore throat":6,"cough":6,
                     "vomiting":4,"diarrhea":4,"sweating":5},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "General Physician",
        "advice": "Rest for 5-7 days. Take paracetamol for fever. Stay well hydrated."
    },
    "Liver Disease": {
        "symptoms": {"nausea":9,"vomiting":9,"abdominal pain":9,
                     "fatigue":7,"appetite loss":7,"weight loss":6,
                     "sweating":4,"depression":3,"swelling":5},
        "age_fn": lambda a: 1.0,
        "risk": "High",
        "specialist": "Hepatologist",
        "advice": "Avoid alcohol completely. Get liver function tests urgently."
    },
    "Migraine": {
        "symptoms": {"headache":10,"nausea":7,"blurred vision":7,
                     "dizziness":6,"vomiting":5,"fatigue":4,
                     "anxiety":3,"insomnia":3},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "Neurologist",
        "advice": "Rest in a dark, quiet room. Apply cold compress to forehead."
    },
    "Obesity": {
        "symptoms": {"weight gain":10,"fatigue":7,"shortness of breath":7,
                     "joint pain":6,"back pain":5,"sweating":4,
                     "dizziness":3,"depression":3},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "Endocrinologist / Nutritionist",
        "advice": "Start with 30-min daily walks. Consult a nutritionist for a diet plan."
    },
    "Parkinson's": {
        "symptoms": {"tremors":10,"muscle pain":8,"dizziness":6,
                     "depression":6,"insomnia":6,"fatigue":5,
                     "weight loss":4,"anxiety":3,"sweating":3},
        "age_fn": lambda a: 3.5 if a > 65 else (1.5 if a > 55 else 0.3),
        "risk": "High",
        "specialist": "Neurologist",
        "advice": "Consult a neurologist. Physical therapy and medication significantly help."
    },
    "Pneumonia": {
        "symptoms": {"fever":10,"cough":9,"shortness of breath":9,
                     "chest pain":8,"sweating":6,"fatigue":5,
                     "nausea":4,"headache":3,"muscle pain":3},
        "age_fn": lambda a: 1.8 if a > 65 else (1.5 if a < 6 else 1.0),
        "risk": "High",
        "specialist": "Pulmonologist",
        "advice": "Go to hospital now. Antibiotics and oxygen support may be required."
    },
    "Sinusitis": {
        "symptoms": {"headache":8,"runny nose":8,"sore throat":7,
                     "cough":6,"sneezing":6,"fatigue":4,
                     "fever":4,"nausea":3},
        "age_fn": lambda a: 1.0,
        "risk": "Low",
        "specialist": "ENT Specialist",
        "advice": "Steam inhalation helps. Nasal decongestant sprays give fast relief."
    },
    "Stroke": {
        "symptoms": {"blurred vision":10,"dizziness":9,"headache":8,
                     "tremors":8,"muscle pain":5,"nausea":4,
                     "fatigue":4,"depression":3,"vomiting":3},
        "age_fn": lambda a: 2.0 if a > 60 else (1.2 if a > 45 else 1.0),
        "risk": "High",
        "specialist": "Neurologist",
        "advice": "Call emergency services immediately. Note exact time symptoms started."
    },
    "Thyroid Disorder": {
        "symptoms": {"weight gain":9,"fatigue":8,"depression":7,
                     "insomnia":7,"anxiety":6,"sweating":6,
                     "weight loss":5,"appetite loss":4,"dizziness":3},
        "age_fn": lambda a: 1.3 if a > 30 else 1.0,
        "risk": "Medium",
        "specialist": "Endocrinologist",
        "advice": "Get a TSH blood test. Thyroid disorders are very manageable with medication."
    },
    "Tuberculosis": {
        "symptoms": {"cough":10,"weight loss":9,"fever":8,"sweating":8,
                     "fatigue":7,"chest pain":5,"shortness of breath":5,
                     "appetite loss":4,"depression":2},
        "age_fn": lambda a: 1.0,
        "risk": "High",
        "specialist": "Pulmonologist",
        "advice": "Isolate immediately. Go to hospital for sputum test and chest X-ray."
    },
    "Ulcer": {
        "symptoms": {"abdominal pain":10,"nausea":8,"vomiting":7,
                     "appetite loss":7,"chest pain":5,"weight loss":4,
                     "fatigue":4,"dizziness":3},
        "age_fn": lambda a: 1.0,
        "risk": "Medium",
        "specialist": "Gastroenterologist",
        "advice": "Avoid NSAIDs and alcohol. Eat small frequent meals. Take prescribed antacids."
    }
}

EMERGENCY = ["chest pain","shortness of breath","blurred vision",
             "tremors","unconscious","severe bleeding"]

def predict(symptoms_list, age, gender):
    """Real prediction: runs the trained RandomForest, not a hand-written scoring table."""
    top_predictions, matched = predict_diseases(age, gender, symptoms_list, top_k=3)
    best_disease, best_proba = top_predictions[0]
    confidence = round(best_proba * 100, 1)
    return best_disease, matched, confidence, top_predictions

@app.route('/predict', methods=['POST','OPTIONS'])
def predict_route():
    if request.method == 'OPTIONS':
        r = jsonify({'status':'ok'})
        r.headers.add('Access-Control-Allow-Origin','*')
        r.headers.add('Access-Control-Allow-Headers','Content-Type')
        r.headers.add('Access-Control-Allow-Methods','POST,OPTIONS')
        return r

    data = request.get_json(silent=True) or {}
    required_fields = ("name", "age", "gender", "symptoms", "email")
    missing_fields = [field for field in required_fields if not str(data.get(field, "")).strip()]
    if missing_fields:
        return jsonify({"error": f"Missing required field(s): {', '.join(missing_fields)}"}), 400

    try:
        age = int(data["age"])
    except (TypeError, ValueError):
        return jsonify({"error": "Age must be a whole number."}), 400
    if not 0 < age <= 150:
        return jsonify({"error": "Age must be between 1 and 150."}), 400

    gender = str(data["gender"]).strip().title()
    if gender not in {"Male", "Female", "Other"}:
        return jsonify({"error": "Gender must be Male, Female, or Other."}), 400
    symptoms_raw = str(data["symptoms"]).strip()

    symptom_list = [s.strip().lower() for s in symptoms_raw.split(',') if s.strip()]
    emergency = any(e in symptoms_raw.lower() for e in EMERGENCY)

    unrecognized = [s for s in symptom_list if s not in KNOWN_SYMPTOMS]

    if emergency:
        # Emergency red flags bypass the model entirely — do not let a probabilistic
        # classifier be the thing standing between a patient and urgent care.
        result = {
            "predictedDisease": None,
            "differential": [],
            "riskLevel": "High",
            "confidenceScore": None,
            "matchedSymptoms": symptom_list,
            "unrecognizedSymptoms": unrecognized,
            "emergencyOverride": True,
            "clinicalSummary": (
                f"Patient aged {age} ({gender}) reports emergency symptoms: {symptoms_raw}. "
                "Immediate medical attention required — do not wait for a model prediction."
            ),
            "recommendation": "Seek emergency medical care immediately.",
            "precautions": [],
            "specialistReferral": "Emergency Department",
            "disclaimer": "This is not a medical diagnosis. Please consult a licensed physician."
        }
        r = jsonify(result)
        r.headers.add('Access-Control-Allow-Origin', '*')
        return r

    disease, matched_syms, confidence, top_predictions = predict(symptom_list, age, gender)
    info = DISEASES.get(disease, {})
    precautions = recommended_precautions_for(disease)
    if not precautions:
        precautions = [info.get("advice", "Consult a qualified healthcare professional.")]

    summary = (
        f"Patient aged {age} ({gender}) presents with: {symptoms_raw}. "
        f"The trained model's top prediction is {disease} ({confidence}% confidence). "
        "Recommend timely medical consultation to confirm."
    )

    result = {
        "predictedDisease": disease,
        "differential": [{"disease": d, "confidence": round(p * 100, 1)} for d, p in top_predictions],
        "riskLevel": info.get("risk", "Low"),
        "confidenceScore": confidence,
        "matchedSymptoms": matched_syms if matched_syms else symptom_list,
        "unrecognizedSymptoms": unrecognized,
        "emergencyOverride": False,
        "clinicalSummary": summary,
        "recommendation": info.get("advice", "Consult a doctor."),
        "precautions": precautions,
        "specialistReferral": info.get("specialist", "General Physician"),
        "disclaimer": "This is not a medical diagnosis. Please consult a licensed physician."
    }

    r = jsonify(result)
    r.headers.add('Access-Control-Allow-Origin','*')
    return r

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"}), 200

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
RESEND_URL = "https://api.resend.com/emails"

@app.route('/send-email', methods=['POST', 'OPTIONS'])
def send_email():
    if request.method == 'OPTIONS':
        r = jsonify({'status': 'ok'})
        r.headers.add('Access-Control-Allow-Origin', '*')
        r.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        r.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return r

    if not RESEND_API_KEY:
        return jsonify({"success": False, "error": "Email delivery is not configured."}), 503

    data = request.json
    patient_name = data.get('name', 'Patient')
    patient_age = data.get('age', '')
    patient_gender = data.get('gender', '')
    patient_symptoms = data.get('symptoms', '')
    patient_email = data.get('email', '')
    predicted_disease = data.get('predictedDisease', '')
    risk_level = data.get('riskLevel', '')
    confidence = data.get('confidenceScore', '')
    matched_symptoms = data.get('matchedSymptoms', [])
    clinical_summary = data.get('clinicalSummary', '')
    recommendation = data.get('recommendation', '')
    specialist = data.get('specialistReferral', '')
    emergency = data.get('emergencyOverride', False)

    risk_color = {
        "High": "#ff4757",
        "Medium": "#ffa502",
        "Low": "#2ed573"
    }.get(risk_level, "#00d4aa")

    emergency_banner = ""
    if emergency:
        emergency_banner = """
        <div style="background:#ff4757;color:white;padding:16px;border-radius:8px;margin-bottom:20px;text-align:center;font-weight:bold;font-size:16px;">
            \u26a0\ufe0f EMERGENCY DETECTED \u2014 Seek Immediate Medical Care
        </div>
        """

    matched_pills = "".join([
        f'<span style="background:#00d4aa22;color:#00d4aa;padding:4px 12px;border-radius:20px;margin:4px;display:inline-block;font-size:13px;border:1px solid #00d4aa;">{s}</span>'
        for s in matched_symptoms
    ])

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#0a0f1e;font-family:'DM Sans',Arial,sans-serif;color:#e2e8f0;">
      <div style="max-width:600px;margin:0 auto;padding:30px 20px;">

        <div style="text-align:center;margin-bottom:30px;">
          <h1 style="color:#00d4aa;font-size:28px;margin:0;">\U0001f48a MediTriage AI</h1>
          <p style="color:#64748b;margin:6px 0 0;">Patient Triage Report</p>
        </div>

        {emergency_banner}

        <div style="background:#111827;border-radius:12px;padding:24px;margin-bottom:20px;border:1px solid #1a2236;">
          <h2 style="color:#e2e8f0;margin:0 0 16px;">Patient Details</h2>
          <table style="width:100%;border-collapse:collapse;">
            <tr><td style="color:#64748b;padding:6px 0;width:140px;">Name</td><td style="color:#e2e8f0;font-weight:600;">{patient_name}</td></tr>
            <tr><td style="color:#64748b;padding:6px 0;">Age</td><td style="color:#e2e8f0;font-weight:600;">{patient_age}</td></tr>
            <tr><td style="color:#64748b;padding:6px 0;">Gender</td><td style="color:#e2e8f0;font-weight:600;">{patient_gender}</td></tr>
            <tr><td style="color:#64748b;padding:6px 0;">Symptoms</td><td style="color:#e2e8f0;font-weight:600;">{patient_symptoms}</td></tr>
          </table>
        </div>

        <div style="background:#111827;border-radius:12px;padding:24px;margin-bottom:20px;border:2px solid {risk_color};text-align:center;">
          <p style="color:#64748b;margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:1px;">Predicted Condition</p>
          <h2 style="color:#e2e8f0;font-size:26px;margin:0 0 12px;">{predicted_disease}</h2>
          <span style="background:{risk_color};color:white;padding:6px 20px;border-radius:20px;font-weight:bold;font-size:14px;">{risk_level} RISK</span>
          <p style="color:#64748b;margin:12px 0 0;font-size:13px;">Confidence: {confidence}%</p>
        </div>

        <div style="background:#111827;border-radius:12px;padding:24px;margin-bottom:20px;border:1px solid #1a2236;">
          <h3 style="color:#e2e8f0;margin:0 0 12px;">Matched Symptoms</h3>
          <div>{matched_pills}</div>
        </div>

        <div style="background:#111827;border-radius:12px;padding:24px;margin-bottom:20px;border:1px solid #1a2236;">
          <h3 style="color:#e2e8f0;margin:0 0 12px;">Clinical Summary</h3>
          <p style="color:#94a3b8;line-height:1.7;margin:0;">{clinical_summary}</p>
        </div>

        <div style="background:#111827;border-radius:12px;padding:24px;margin-bottom:20px;border:1px solid #1a2236;">
          <h3 style="color:#e2e8f0;margin:0 0 16px;">Recommendations</h3>
          <div style="display:flex;align-items:flex-start;margin-bottom:12px;">
            <span style="color:#00d4aa;margin-right:10px;font-size:18px;">\u2713</span>
            <p style="color:#94a3b8;margin:0;line-height:1.6;">{recommendation}</p>
          </div>
          <div style="display:flex;align-items:center;margin-top:12px;padding-top:12px;border-top:1px solid #1a2236;">
            <span style="color:#00d4aa;margin-right:10px;font-size:18px;">\U0001fa7a</span>
            <p style="color:#94a3b8;margin:0;">See a <strong style="color:#e2e8f0;">{specialist}</strong></p>
          </div>
        </div>

        <div style="text-align:center;padding:20px;color:#64748b;font-size:12px;border-top:1px solid #1a2236;margin-top:20px;">
          <p style="margin:0;">This report is generated by MediTriage AI for preliminary assessment only.</p>
          <p style="margin:6px 0 0;">Always consult a qualified medical professional for diagnosis and treatment.</p>
        </div>

      </div>
    </body>
    </html>
    """

    try:
        response = http_requests.post(
            RESEND_URL,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "from": "MediTriage AI <onboarding@resend.dev>",
                "to": [patient_email],
                "subject": f"\U0001f3e5 Your MediTriage Report \u2014 {predicted_disease} ({risk_level} Risk)",
                "html": html_body
            }
        )

        if response.status_code == 200 or response.status_code == 201:
            r = jsonify({"success": True, "message": "Email sent successfully"})
        else:
            r = jsonify({"success": False, "error": response.text})

        r.headers.add('Access-Control-Allow-Origin', '*')
        return r

    except Exception as e:
        r = jsonify({"success": False, "error": str(e)})
        r.headers.add('Access-Control-Allow-Origin', '*')
        return r, 500



# ═══════════════════════════════════════════════════════════════════════════════
#  IMAGE UPLOAD — POST /api/images/upload
# ═══════════════════════════════════════════════════════════════════════════════
@app.route('/api/images/upload', methods=['POST', 'OPTIONS'])
def upload_image():
    """
    Secure image intake pipeline:
      1. 8 MB size guard
      2. Real MIME check via python-magic (reject non-image)
      3. Pillow re-save → strips all EXIF metadata
      4. Fernet encrypt → write to image_store/<uuid>.enc
      5. DB row: {image_id, patient_id, uploaded_at} only — no path, no name
    """
    if request.method == 'OPTIONS':
        r = jsonify({'status': 'ok'})
        r.headers.add('Access-Control-Allow-Origin', '*')
        r.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        r.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return r

    # ── 1. Presence check ────────────────────────────────────────────────────
    img_file = request.files.get('image')
    if not img_file:
        return jsonify({'error': 'No image file provided.'}), 400

    patient_id = request.form.get('patient_id', '').strip()
    if not patient_id:
        return jsonify({'error': 'patient_id is required.'}), 400

    # ── 1.5 Consent Verification ──────────────────────────────────────────────
    # Reject upload if patient hasn't explicitly consented
    has_consent = Consent.query.filter_by(patient_id=patient_id).first()
    if not has_consent:
        return jsonify({'error': 'Explicit consent is required before uploading data.'}), 403

    # ── 2. Size guard (read up to limit+1 to detect oversized without loading all) ──
    raw_bytes = img_file.read(MAX_IMAGE_BYTES + 1)
    if len(raw_bytes) == 0:
        return jsonify({'error': 'Empty file received.'}), 400
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        return jsonify({'error': 'Image exceeds the 8 MB size limit.'}), 413

    # ── 3. Real MIME type via python-magic (ignores Content-Type header) ─────
    try:
        detected_mime = magic.from_buffer(raw_bytes, mime=True)
    except Exception:
        return jsonify({'error': 'File type detection failed.'}), 500

    if detected_mime not in ALLOWED_MIMES:
        return jsonify({
            'error': (
                f'File type "{detected_mime}" is not accepted. '
                'Only JPEG and PNG images are allowed.'
            )
        }), 415

    # ── 4. Pillow re-save — strips EXIF as a guaranteed side effect ──────────
    try:
        buf_in = io.BytesIO(raw_bytes)
        img = PilImage.open(buf_in)
        img.verify()                            # raises on corrupt files

        buf_in.seek(0)                          # verify() closes the stream
        img = PilImage.open(buf_in)

        pil_fmt = MIME_TO_PIL_FMT[detected_mime]
        if pil_fmt == 'JPEG':
            img = img.convert('RGB')            # drop alpha channel if present

        buf_out = io.BytesIO()
        # exif=b'' explicitly overwrites any surviving metadata chunk
        save_kwargs = {'format': pil_fmt}
        if pil_fmt == 'JPEG':
            save_kwargs['exif'] = b''
            save_kwargs['quality'] = 92
        img.save(buf_out, **save_kwargs)
        clean_bytes = buf_out.getvalue()
    except UnidentifiedImageError:
        return jsonify({'error': 'File could not be opened as an image.'}), 422
    except Exception:
        return jsonify({'error': 'Image processing failed. The file may be corrupt.'}), 422

    # ── 5. Fernet encryption ─────────────────────────────────────────────────
    try:
        cipher = _image_cipher()
        encrypted = cipher.encrypt(clean_bytes)
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 503
    except Exception:
        return jsonify({'error': 'Encryption failed. Contact the administrator.'}), 500

    # ── 6. Persist: UUID key → encrypted blob on disk + metadata row in DB ───
    image_id  = str(uuid.uuid4())
    blob_path = IMAGE_STORE / f'{image_id}.enc'
    blob_path.write_bytes(encrypted)

    row = PatientImage(id=image_id, patient_id=patient_id)
    try:
        db.session.add(row)
        db.session.commit()
    except Exception:
        blob_path.unlink(missing_ok=True)       # roll back the file write
        db.session.rollback()
        return jsonify({'error': 'Database write failed.'}), 500

    r = jsonify({
        'image_id':    image_id,
        'uploaded_at': row.uploaded_at.isoformat(),
    })
    r.headers.add('Access-Control-Allow-Origin', '*')
    return r, 201


# ═══════════════════════════════════════════════════════════════════════════════
#  IMAGE RETRIEVAL — GET /api/images/<image_id>
# ═══════════════════════════════════════════════════════════════════════════════
@app.route('/api/images/<image_id>', methods=['GET'])
@jwt_required()
def get_image(image_id):
    """
    Decrypt and serve a stored image.
    Role-based ownership check enforced:
    - Doctors can only view images if they are the assigned doctor for the patient.
    - Patients can view their own images (not fully implemented in auth yet, but conceptual).
    """
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    role = claims.get('role', 'patient')

    # Validate UUID format to prevent path traversal
    try:
        uuid.UUID(image_id)
    except ValueError:
        return jsonify({'error': 'Invalid image ID.'}), 400

    row = db.session.get(PatientImage, image_id)
    if not row:
        return jsonify({'error': 'Image not found.'}), 404
        
    patient = db.session.get(Patient, row.patient_id)
    if not patient:
        return jsonify({'error': 'Associated patient not found.'}), 404

    # Ownership check
    if role == 'doctor' and patient.assigned_doctor_id != current_user_id:
         return jsonify({'error': 'Unauthorized: Patient not assigned to your queue.'}), 403
    elif role == 'patient' and patient.id != current_user_id:
         return jsonify({'error': 'Unauthorized: You can only view your own images.'}), 403
    elif role == 'hospital_booking':
         return jsonify({'error': 'Unauthorized: Hospital booking role cannot view images.'}), 403

    blob_path = IMAGE_STORE / f'{image_id}.enc'
    if not blob_path.exists():
        return jsonify({'error': 'Image data not found on disk.'}), 404

    try:
        cipher    = _image_cipher()
        decrypted = cipher.decrypt(blob_path.read_bytes())
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 503
    except InvalidToken:
        return jsonify({'error': 'Decryption failed: key mismatch or corrupt data.'}), 500
    except Exception:
        return jsonify({'error': 'Decryption failed.'}), 500

    # Infer MIME from Pillow to avoid trusting the stored blob header
    try:
        with PilImage.open(io.BytesIO(decrypted)) as img:
            fmt      = img.format or 'JPEG'
            mime_out = 'image/png' if fmt == 'PNG' else 'image/jpeg'
    except Exception:
        mime_out = 'image/jpeg'

    # ── Audit Log ────────────────────────────────────────────────────────────
    # Log access before returning the payload
    log_access(current_user_id, 'image', image_id, 'read')

    return send_file(
        io.BytesIO(decrypted),
        mimetype=mime_out,
        as_attachment=False,
        download_name=f'{image_id}.jpg',
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTH & ROLE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'patient') # In a real app, don't let anyone register as admin/doctor

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    new_user = User(
        email=email,
        password_hash=generate_password_hash(password),
        role=role
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User created successfully', 'user_id': new_user.id}), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip()
    password = data.get('password', '')

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid email or password'}), 401

    access_token = create_access_token(identity=user.id, additional_claims={'role': user.role})
    return jsonify({'access_token': access_token, 'role': user.role}), 200


@app.route('/api/consent', methods=['POST', 'OPTIONS'])
@app.route('/consent', methods=['POST', 'OPTIONS'])
def capture_consent():
    """
    Capture patient consent before using camera/saving data.
    """
    if request.method == 'OPTIONS':
        r = jsonify({'status': 'ok'})
        r.headers.add('Access-Control-Allow-Origin', '*')
        r.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        r.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return r

    data = request.get_json(silent=True) or {}
    patient_id = data.get('patient_id', '').strip()
    purpose = data.get('purpose', 'medical_triage')
    consent_version = data.get('consent_version', '1.0')

    if not patient_id:
         return jsonify({'error': 'patient_id is required'}), 400

    new_consent = Consent(
        patient_id=patient_id,
        purpose=purpose,
        consent_version=consent_version
    )
    db.session.add(new_consent)
    db.session.commit()
    
    r = jsonify({'message': 'Consent recorded', 'consent_id': new_consent.id})
    r.headers.add('Access-Control-Allow-Origin', '*')
    return r, 201


@app.route('/api/booking/patient/<patient_id>', methods=['GET'])
@jwt_required()
def get_hospital_booking_patient(patient_id):
    """
    Hospital booking route: explicitly excludes symptom text and images.
    Returns only name, contact, and risk_level (mocked risk for now).
    """
    claims = get_jwt()
    if claims.get('role') not in ('hospital_booking', 'admin'):
        return jsonify({'error': 'Unauthorized: Hospital booking role required'}), 403
        
    patient = db.session.get(Patient, patient_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
        
    # Serialize ONLY the allowed fields
    return jsonify({
        'id': patient.id,
        'name': patient.name,
        'phone': patient.phone,
        'age': patient.age,
        'gender': patient.gender,
        'risk_level': 'High' # Mocked for now; this would come from a proper medical record relation
    }), 200


@app.route('/api/doctor/patient/<patient_id>', methods=['GET'])
@jwt_required()
def get_doctor_patient(patient_id):
    """
    Doctor facing route: Returns full patient details (including symptoms).
    Enforces ownership check.
    """
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    if claims.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized: Doctor role required'}), 403

    patient = db.session.get(Patient, patient_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    # Ownership check
    if patient.assigned_doctor_id != current_user_id:
        return jsonify({'error': 'Unauthorized: Patient not assigned to your queue'}), 403

    # ── Audit Log ────────────────────────────────────────────────────────────
    log_access(current_user_id, 'patient', patient.id, 'read')

    return jsonify({
        'id': patient.id,
        'name': patient.name,
        'phone': patient.phone,
        'age': patient.age,
        'gender': patient.gender,
        'symptoms': patient.symptoms,
        'created_at': patient.created_at.isoformat()
    }), 200


@app.route('/api/my-data/<patient_id>', methods=['DELETE'])
@jwt_required()
def delete_my_data(patient_id):
    """
    Patient-facing route: Immediately deletes the patient's record and images.
    Enforces ownership check.
    """
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    if claims.get('role') != 'patient' or current_user_id != patient_id:
        return jsonify({'error': 'Unauthorized: You can only delete your own data'}), 403

    patient = db.session.get(Patient, patient_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    # 1. Delete image blobs from disk & PatientImage rows
    images = PatientImage.query.filter_by(patient_id=patient_id).all()
    for img in images:
        blob_path = IMAGE_STORE / f'{img.id}.enc'
        blob_path.unlink(missing_ok=True)
        db.session.delete(img)

    # 2. Delete consents
    Consent.query.filter_by(patient_id=patient_id).delete()

    # 3. Delete patient record
    db.session.delete(patient)
    
    # 4. Audit Log
    log_access(current_user_id, 'patient', patient_id, 'delete')
    
    db.session.commit()
    return jsonify({'message': 'All patient data deleted successfully'}), 200


# ═══════════════════════════════════════════════════════════════════════════════
#  RETENTION & PURGE BACKGROUND JOB
# ═══════════════════════════════════════════════════════════════════════════════

def purge_old_data():
    """Deletes images and patient data older than 90 days."""
    with app.app_context():
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)
        
        # Purge old images
        old_images = PatientImage.query.filter(
            PatientImage.uploaded_at < cutoff_date,
            PatientImage.retention_hold == False
        ).all()
        
        for img in old_images:
            blob_path = IMAGE_STORE / f'{img.id}.enc'
            blob_path.unlink(missing_ok=True)
            db.session.delete(img)
            log_access('system', 'image', img.id, 'auto_delete')
            
        db.session.commit()

# Start the scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=purge_old_data, trigger="interval", days=1)
scheduler.start()

import atexit
atexit.register(lambda: scheduler.shutdown())


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5051, debug=False)