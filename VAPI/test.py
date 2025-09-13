#!/usr/bin/env python3
"""
Record a Vapi voice agent to WAV by:
  1) Calling your FastAPI /start-narration to get narration_text
  2) Creating a Vapi WebSocket call (assistant speaks first)
  3) Connecting to the websocket and saving incoming PCM audio as a WAV

Usage:
  export VAPI_API_KEY=...
  python record_vapi_ws.py --backend http://localhost:8000 \
      --file-path /mnt/data/sample.mp4 \
      --assistant-id YOUR_VAPI_ASSISTANT_ID \
      --out narration.wav \
      --duration 12

Notes:
  - duration is a simple max seconds to record before hanging up (safety stop).
  - We configure Vapi to stream PCM s16le @ 16000 Hz (mono), which we wrap into WAV.
  - Requires: pip install requests websocket-client
"""

import os
import argparse
import json
import time
import struct
import wave
import requests
from websocket import WebSocketApp  # from websocket-client

SAMPLE_RATE = 16000  # matches our Vapi request (PCM s16le 16k)
SAMPLE_WIDTH = 2     # 16-bit = 2 bytes
CHANNELS = 1         # mono

def write_wav(filename: str, pcm_bytes: bytes, sample_rate=SAMPLE_RATE):
    """Save raw PCM (16-bit little-endian mono) to a WAV file."""
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)

def start_websocket_call(vapi_api_key: str, assistant_id: str, narration_text: str, vapi_base="https://api.vapi.ai"):
    """
    Create a Vapi WebSocket call that will stream audio back to us.
    We set firstMessage to make the agent start speaking immediately.
    Returns the websocketCallUrl to connect to.
    """
    url = f"{vapi_base}/call"
    headers = {
        "authorization": f"Bearer {vapi_api_key}",
        "content-type": "application/json",
    }

    system_prompt = (
        "You are a VR narrator. Be concise, warm, and vivid. "
        "Use ONLY the provided narration unless the user asks for more.\n\n"
        f"NARRATION:\n{narration_text}"
    )

    body = {
        "assistantId": assistant_id,
        "overrides": {
            "systemPrompt": system_prompt,
            "firstMessage": narration_text
        },
        "transport": {
            "provider": "vapi.websocket",
            "audioFormat": {             # request raw PCM so we can save as WAV
                "format": "pcm_s16le",
                "container": "raw",
                "sampleRate": SAMPLE_RATE
            }
        }
    }

    resp = requests.post(url, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    # Per docs, look for transport.websocketCallUrl
    ws_url = (data.get("transport") or {}).get("websocketCallUrl")
    if not ws_url:
        raise RuntimeError(f"Unexpected /call response, no websocketCallUrl:\n{json.dumps(data, indent=2)[:800]}")
    return ws_url

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", required=True, help="Your FastAPI base URL (e.g. http://localhost:8000)")
    ap.add_argument("--file-path", required=True, help="ABSOLUTE path to the video ON THE BACKEND machine")
    ap.add_argument("--assistant-id", required=True, help="Vapi Assistant ID to use for the voice")
    ap.add_argument("--out", default="narration.wav", help="Output WAV filename")
    ap.add_argument("--user-name", default="Guest")
    ap.add_argument("--style", default="warm, concise, present tense")
    ap.add_argument("--duration", type=int, default=12, help="Max seconds to record before hanging up")
    ap.add_argument("--vapi-base", default="https://api.vapi.ai")
    args = ap.parse_args()

    vapi_key = os.getenv("VAPI_API_KEY")
    if not vapi_key:
        raise SystemExit("Set VAPI_API_KEY in your environment.")

    # 1) Get narration_text from your FastAPI
    payload = {"file_path": args.file_path, "user_name": args.user_name, "style": args.style}
    r = requests.post(f"{args.backend}/start-narration", json=payload, timeout=600)
    if r.status_code >= 400:
        raise SystemExit(f"/start-narration failed: {r.status_code} {r.text[:500]}")
    data = r.json()
    narration_text = data.get("narration_text") or ""
    if not narration_text:
        raise SystemExit("Backend returned no narration_text")
    print("\n--- Narration text ---")
    print(narration_text)
    print("----------------------\n")

    # 2) Create a Vapi WebSocket call (agent will speak first)
    ws_url = start_websocket_call(
        vapi_api_key=vapi_key,
        assistant_id=args.assistant_id,
        narration_text=narration_text,
        vapi_base=args.vapi_base
    )
    print(f"WebSocket URL: {ws_url}")

    # 3) Connect and record binary PCM frames → WAV
    pcm_buffer = bytearray()
    start_time = time.time()
    done = {"flag": False}

    def on_open(ws):
        print("WebSocket opened.")

    def on_message(ws, message):
        # Vapi sends either:
        #  - Binary audio data (our PCM)
        #  - Text JSON control messages
        if isinstance(message, (bytes, bytearray)):
            # Append raw PCM bytes
            pcm_buffer.extend(message)
        else:
            # Control JSON as text
            try:
                obj = json.loads(message)
                # You can inspect events here if needed
                # print("CTRL:", obj)
            except Exception:
                # Unexpected text payload; ignore
                pass

        # Stop if we hit duration
        if time.time() - start_time >= args.duration and not done["flag"]:
            done["flag"] = True
            try:
                # Send hangup control message, then close
                ws.send(json.dumps({"type": "hangup"}))
            except Exception:
                pass
            ws.close()

    def on_error(ws, err):
        print("WebSocket error:", err)

    def on_close(ws, code, reason):
        print(f"WebSocket closed: code={code} reason={reason}")

    ws = WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        header=[f"authorization: Bearer {vapi_key}"],  # auth header for WS (if required)
    )

    # Run until closed
    ws.run_forever()

    # 4) Save to WAV
    if pcm_buffer:
        write_wav(args.out, bytes(pcm_buffer), sample_rate=SAMPLE_RATE)
        print(f"Saved WAV: {args.out}")
    else:
        print("No audio received; WAV not written.")

if __name__ == "__main__":
    main()
