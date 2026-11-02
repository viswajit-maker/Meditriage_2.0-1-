"""
FastAPI Chatbot Server for MediTriage AI
=========================================
Uses the trained symptom2disease_model.pkl for disease prediction
and the Gemini API for conversational reasoning.

Flow (at most 2 conversation turns):
  Turn 1: User describes symptoms → model predicts top diseases →
           Gemini asks one focused follow-up question.
  Turn 2: User answers → model re-predicts with enriched symptoms →
           Final diagnosis with risk level and recommendation.
"""

import json
import os
import pickle
import uuid
from pathlib import Path
from typing import Optional

import numpy as np
import requests as http_requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Paths ────────────────────────────────────────────────────────────────────
CHATBOT_DIR = Path(__file__).resolve().parent
MODEL_PATH = CHATBOT_DIR / "symptom2disease_model.pkl"
API_KEY_PATH = CHATBOT_DIR / "apikey.txt"

# ── Load trained model ───────────────────────────────────────────────────────
if not MODEL_PATH.exists():
    raise FileNotFoundError(f"Model not found at {MODEL_PATH}")

with open(MODEL_PATH, "rb") as f:
    MODEL = pickle.load(f)

print(f"[chatbot] Loaded model from {MODEL_PATH}")
print(f"[chatbot] Model classes ({len(MODEL.classes_)}): {list(MODEL.classes_[:5])}...")

# ── Load Gemini API key ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY and API_KEY_PATH.exists():
    GEMINI_API_KEY = API_KEY_PATH.read_text(encoding="utf-8").strip()
if not GEMINI_API_KEY:
    print("[chatbot] INFO: No Gemini API key found. Conversational reasoning fallback enabled.")

# ── Disease risk mapping ─────────────────────────────────────────────────────
HIGH_RISK_DISEASES = {
    "Heart Attack", "Stroke", "Pneumonia", "Tuberculosis", "Hepatitis",
    "Malaria", "Dengue", "Typhoid", "Jaundice", "AIDS",
    "Paralysis (brain hemorrhage)", "Heart attack",
}
MEDIUM_RISK_DISEASES = {
    "Diabetes", "Hypertension", "Bronchial Asthma", "Chronic cholestasis",
    "Peptic ulcer diseae", "Urinary tract infection", "Gastroenteritis",
    "Arthritis", "Hyperthyroidism", "Hypothyroidism",
}

def get_risk_level(disease: str, confidence: float) -> str:
    """Determine risk level based on disease and confidence."""
    if disease in HIGH_RISK_DISEASES or confidence > 0.85:
        return "High"
    if disease in MEDIUM_RISK_DISEASES or confidence > 0.5:
        return "Medium"
    return "Low"

def get_urgency_advice(risk: str) -> str:
    if risk == "High":
        return "⚠️ See a doctor IMMEDIATELY. This condition may require urgent medical attention."
    if risk == "Medium":
        return "🩺 Please schedule a doctor's appointment within the next 1-2 days."
    return "💊 This appears manageable. Monitor symptoms and consult a doctor if they worsen."


# ── In-memory session store ──────────────────────────────────────────────────
sessions: dict = {}


# ── ML prediction helper ────────────────────────────────────────────────────
def predict_top_diseases(symptom_text: str, top_k: int = 3):
    """Use the trained pipeline to predict diseases from symptom text."""
    probs = MODEL.predict_proba([symptom_text])[0]
    top_idx = np.argsort(probs)[::-1][:top_k]
    results = []
    for i in top_idx:
        results.append({
            "disease": MODEL.classes_[i],
            "confidence": round(float(probs[i]) * 100, 1),
        })
    return results


# ── Gemini API helper ────────────────────────────────────────────────────────
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

def ask_gemini(prompt: str) -> str:
    """Call Gemini API for reasoning / follow-up generation."""
    key = os.environ.get("GEMINI_API_KEY", "") or GEMINI_API_KEY
    if not key:
        return ""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 300},
    }
    try:
        resp = http_requests.post(
            GEMINI_URL,
            params={"key": key},
            json=payload,
            timeout=4,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[chatbot] Gemini error: {e}")
    return ""


# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="MediTriage Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    turn: int
    is_final: bool
    diagnosis: Optional[dict] = None


@app.get("/chatbot/health")
def chatbot_health():
    return {"status": "ok", "model_loaded": True, "classes": len(MODEL.classes_)}


@app.post("/chatbot/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Main chat endpoint. Handles at most 2 turns:
      Turn 1 → Predict + ask follow-up
      Turn 2 → Re-predict with enriched info + final diagnosis
    """
    # ── Session handling ─────────────────────────────────────────────────────
    sid = req.session_id or str(uuid.uuid4())
    session = sessions.get(sid, {"turn": 0, "symptoms": "", "history": []})
    session["turn"] += 1
    turn = session["turn"]

    user_message = req.message.strip()
    session["history"].append({"role": "user", "text": user_message})

    # ── TURN 1: Initial symptom intake ───────────────────────────────────────
    if turn == 1:
        session["symptoms"] = user_message

        # Run ML prediction
        predictions = predict_top_diseases(user_message, top_k=3)
        session["initial_predictions"] = predictions

        # Ask Gemini for a focused follow-up question
        top_disease = predictions[0]["disease"]
        top_conf = predictions[0]["confidence"]

        gemini_prompt = f"""You are a medical triage chatbot. A patient described these symptoms:
"{user_message}"

Based on analysis, the most likely conditions are:
1. {predictions[0]['disease']} ({predictions[0]['confidence']}%)
2. {predictions[1]['disease']} ({predictions[1]['confidence']}%)
3. {predictions[2]['disease']} ({predictions[2]['confidence']}%)

Ask ONE short, focused follow-up question to help narrow down the diagnosis.
The question should help differentiate between the top conditions.
Be empathetic and professional. Do NOT reveal the predicted diseases yet.
Keep it to 1-2 sentences maximum."""

        follow_up = ask_gemini(gemini_prompt)
        if not follow_up:
            follow_up = (
                f"Based on your symptoms, I am evaluating conditions such as {predictions[0]['disease']} or {predictions[1]['disease']}. "
                f"Could you tell me how long you have experienced these symptoms, and if you have any other associated sensations (such as fever, chills, fatigue, or localized pain)?"
            )

        reply = (
            f"I understand you're experiencing these symptoms. Let me analyze them.\n\n"
            f"{follow_up}"
        )

        session["history"].append({"role": "assistant", "text": reply})
        sessions[sid] = session

        return ChatResponse(
            session_id=sid,
            reply=reply,
            turn=turn,
            is_final=False,
            diagnosis=None,
        )

    # ── TURN 2: Final diagnosis ──────────────────────────────────────────────
    else:
        # Combine original symptoms with follow-up info
        enriched_symptoms = f"{session['symptoms']}. {user_message}"
        predictions = predict_top_diseases(enriched_symptoms, top_k=3)

        top = predictions[0]
        risk_level = get_risk_level(top["disease"], top["confidence"] / 100)
        urgency = get_urgency_advice(risk_level)

        # Ask Gemini for a final summary
        gemini_prompt = f"""You are a medical triage chatbot providing a final assessment.

Patient's initial symptoms: "{session['symptoms']}"
Follow-up information: "{user_message}"

ML Model predictions:
1. {predictions[0]['disease']} ({predictions[0]['confidence']}% confidence)
2. {predictions[1]['disease']} ({predictions[1]['confidence']}% confidence)
3. {predictions[2]['disease']} ({predictions[2]['confidence']}% confidence)

Risk Level: {risk_level}

Provide a brief, empathetic final assessment in 2-3 sentences:
- State the most likely condition
- Explain the risk level
- Give one key precaution/recommendation
Do NOT say "I am an AI" or add disclaimers. Be direct and caring."""

        gemini_summary = ask_gemini(gemini_prompt)
        if not gemini_summary:
            gemini_summary = (
                f"Based on your symptoms and description, the clinical pattern most closely matches **{top['disease']}** "
                f"with a **{top['confidence']}%** statistical correlation.\n\n"
                f"The evaluated risk level is **{risk_level}**."
            )

        reply = (
            f"{gemini_summary}\n\n"
            f"---\n"
            f"**{urgency}**\n\n"
            f"*This is an AI-assisted preliminary assessment. "
            f"Always consult a qualified healthcare professional for proper diagnosis and treatment.*"
        )

        diagnosis = {
            "predicted_disease": top["disease"],
            "confidence": top["confidence"],
            "risk_level": risk_level,
            "urgency": urgency,
            "differential": predictions,
        }

        session["history"].append({"role": "assistant", "text": reply})
        sessions[sid] = session

        return ChatResponse(
            session_id=sid,
            reply=reply,
            turn=turn,
            is_final=True,
            diagnosis=diagnosis,
        )


@app.post("/chatbot/reset")
def reset_session(req: ChatRequest):
    """Reset a chat session to start over."""
    sid = req.session_id
    if sid and sid in sessions:
        del sessions[sid]
    return {"status": "ok", "message": "Session reset"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
