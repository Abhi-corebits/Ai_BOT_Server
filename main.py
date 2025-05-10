from flask import Flask, request, render_template
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
import os
import requests
import uuid

app = Flask(__name__)

# === ENV variables ===
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
VOICE_ID = os.environ.get("ELEVEN_VOICE_ID")  # e.g., "Rishi"
WELCOME_MP3 = "static/welcome.mp3"

client = Client(TWILIO_SID, TWILIO_TOKEN)

# === Homepage ===
@app.route("/")
def index():
    return render_template("index.html")

# === Trigger outgoing call ===
@app.route("/call", methods=["POST"])
def call():
    to_number = request.form["to"]
    call = client.calls.create(
        to=to_number,
        from_=TWILIO_NUMBER,
        url=f"{request.url_root}voice"
    )
    return f"Calling {to_number}..."

# === First response with pre-recorded welcome ===
@app.route("/voice", methods=["POST"])
def voice():
    resp = VoiceResponse()
    resp.play(f"/{WELCOME_MP3}")
    resp.record(timeout=5, max_length=15, action="/process_audio", play_beep=False)
    return str(resp)

# === Handle user question ===
@app.route("/process_audio", methods=["POST"])
def process_audio():
    recording_url = request.form["RecordingUrl"]
    audio_file = f"static/{uuid.uuid4()}.wav"
    os.system(f"curl {recording_url}.wav -o {audio_file}")

    # Transcribe using Whisper
    with open(audio_file, "rb") as f:
        whisper = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": f},
            data={"model": "whisper-1"}
        )
    user_input = whisper.json()["text"]

    # Generate reply with Groq (GPT-3.5/4-turbo)
    chat = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": "mixtral-8x7b-32768",
            "messages": [
                {"role": "system", "content": "You are a helpful Indian AI college guide named Aarav."},
                {"role": "user", "content": user_input}
            ]
        }
    )
    reply = chat.json()["choices"][0]["message"]["content"]

    # Convert GPT reply to speech (ElevenLabs)
    tts = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
        headers={
            "xi-api-key": os.environ["ELEVEN_API_KEY"],
            "Content-Type": "application/json"
        },
        json={
            "text": reply,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.7}
        }
    )
    mp3_path = f"static/{uuid.uuid4()}.mp3"
    with open(mp3_path, "wb") as f:
        f.write(tts.content)

    # Play and loop
    resp = VoiceResponse()
    resp.play(f"/{mp3_path}")
    resp.record(timeout=5, max_length=15, action="/process_audio", play_beep=False)
    return str(resp)

# === Start app ===
if __name__ == "__main__":
    app.run(debug=True)
