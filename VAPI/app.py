# app.py
import os
import time
import tempfile
import json
from typing import Optional

import requests
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# ====== CONFIG (env) ======
# export GEMINI_API_KEY=...
# export VAPI_API_KEY=...
# export VAPI_ASSISTANT_ID=...
# (Optionally) export VAPI_BASE=https://api.vapi.ai
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBj-XGMHpmeOMaNS7IOhOhmds-aYOfuC0U")
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "fc02f0e0-2c78-46ac-b13f-bbb25294a497")
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "3516e5c6-9c17-49d3-87ce-cf14901e1df0")
VAPI_BASE = os.getenv("VAPI_BASE", "https://api.vapi.ai")

if not GEMINI_API_KEY or not VAPI_API_KEY or not VAPI_ASSISTANT_ID:
    raise RuntimeError("Please set GEMINI_API_KEY, VAPI_API_KEY, and VAPI_ASSISTANT_ID env vars")

genai.configure(api_key=GEMINI_API_KEY)

# ====== FASTAPI ======
app = FastAPI(title="Live Narration Backend", version="1.0")

# allow local dev from Unity/localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====== MODELS ======
class StartByPathIn(BaseModel):
    file_path: str
    user_name: Optional[str] = "Guest"
    style: Optional[str] = "warm, concise, present tense"

class StartOut(BaseModel):
    session_id: str
    vapi_session_raw: dict
    narration_text: str

# ====== GEMINI HELPERS ======
def _wait_for_gemini_file_active(file_obj, timeout_s: int = 120):
    """Polls Gemini file state until ACTIVE (simple helper)."""
    start = time.time()
    while time.time() - start < timeout_s:
        file_obj = genai.get_file(file_obj.name)
        if file_obj.state.name == "ACTIVE":
            return file_obj
        if file_obj.state.name == "FAILED":
            raise RuntimeError(f"Gemini file processing failed: {file_obj.error}")
        time.sleep(1)
    raise TimeoutError("Timed out waiting for Gemini to process the uploaded file.")

def summarize_video_with_gemini_file(file_path: str, style: str) -> str:
    """Uploads a local video to Gemini and gets a short narrator-style description."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found on server: {file_path}")

    # Upload video to Gemini
    uploaded = genai.upload_file(file_path)
    uploaded = _wait_for_gemini_file_active(uploaded)

    # Ask for a short narration
    model = genai.GenerativeModel("gemini-1.5-pro")
    prompt = (
        "Describe this video like a cinematic VR narrator. "
        "Write 1–3 short sentences, present tense, grounded in what’s visible/obvious; "
        f"style: {style}. No lists, no timestamps—just a flowing narration."
    )
    res = model.generate_content([uploaded, prompt])
    text = (res.text or "").strip()
    if not text:
        text = "We’re stepping into the scene. Light and motion bring a familiar moment back to life."
    return text

# ====== VAPI HELPERS ======
def vapi_create_session(narration_text: str, user_name: Optional[str]) -> dict:
    """
    Creates a Vapi realtime session. We pass narration_text via overrides so the
    assistant starts speaking with this context. Adjust path if your Vapi account
    uses a different API base or version.
    """
    url = f"{VAPI_BASE}/session"  # if your workspace uses /v1/sessions, change here
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "You are a VR narrator. Be concise, warm, and vivid. "
        "Use the provided narration as core context; do not invent specifics beyond it unless asked.\n\n"
        f"NARRATION:\n{narration_text}"
    )

    body = {
        "assistantId": VAPI_ASSISTANT_ID,
        "overrides": {
            "systemPrompt": system_prompt,
            # Kick off speaking as soon as the client connects
            "firstMessage": narration_text
        }
    }
    if user_name:
        # Optional: only if your Assistant defines variables
        body["overrides"]["variableValues"] = {"name": user_name}

    resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Vapi session create failed: {resp.text[:500]}")
    return resp.json()

def vapi_send_chat(session_id: str, text: str) -> dict:
    """Sends a message into an existing Vapi session so it speaks in response."""
    url = f"{VAPI_BASE}/chat"  # adjust if your account uses /v1/chat
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {"sessionId": session_id, "input": text}
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Vapi chat failed: {resp.text[:500]}")
    return resp.json()

# ====== ROUTES ======
@app.post("/start-narration", response_model=StartOut)
def start_narration_by_path(payload: StartByPathIn):
    """
    Dev-friendly route: assume the video already exists on the server filesystem.
    """
    narration = summarize_video_with_gemini_file(payload.file_path, payload.style or "warm")
    vapi_session = vapi_create_session(narration, payload.user_name)
    session_id = vapi_session.get("id") or vapi_session.get("_id") or vapi_session.get("sessionId") or ""
    if not session_id:
        raise HTTPException(status_code=500, detail=f"Unexpected Vapi response: {json.dumps(vapi_session)[:500]}")
    return StartOut(session_id=session_id, vapi_session_raw=vapi_session, narration_text=narration)

@app.post("/start-narration-upload", response_model=StartOut)
def start_narration_upload(file: UploadFile = File(...), user_name: str = Form("Guest"), style: str = Form("warm, concise, present tense")):
    """
    Production-style route: upload a video file as multipart/form-data.
    """
    # Save to a temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename or "")[-1]) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        narration = summarize_video_with_gemini_file(tmp_path, style or "warm")
        vapi_session = vapi_create_session(narration, user_name)
        session_id = vapi_session.get("id") or vapi_session.get("_id") or vapi_session.get("sessionId") or ""
        if not session_id:
            raise HTTPException(status_code=500, detail=f"Unexpected Vapi response: {json.dumps(vapi_session)[:500]}")
        return StartOut(session_id=session_id, vapi_session_raw=vapi_session, narration_text=narration)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

@app.post("/send-message")
def send_message(session_id: str = Form(...), text: str = Form(...)):
    """
    Optional helper: push a follow-up line into the live session.
    Unity can call this when the player hits a trigger (e.g., 'Describe the photo wall').
    """
    return vapi_send_chat(session_id, text)

# Run: uvicorn app:app --reload --port 8000