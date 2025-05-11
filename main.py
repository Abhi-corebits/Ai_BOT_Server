from flask import Flask, request, send_file, Response, render_template, redirect, url_for
from twilio.twiml.voice_response import VoiceResponse
import requests
import os
from dotenv import load_dotenv
import uuid

load_dotenv()

app = Flask(__name__)

# Constants
WELCOME_MP3_URL = "https://ai-voice-bot-production-1ecc.up.railway.app/static/welcome.mp3"
REPLY_AUDIO_PATH = "static/response.mp3"

# Home page route to serve index.html
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

# Endpoint to start the call
@app.route("/call", methods=["POST"])
def start_call():
    from twilio.rest import Client
    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

    call = client.calls.create(
        twiml=f'<Response><Play>{WELCOME_MP3_URL}</Play><Pause length="2"/><Record maxLength="10" action="/process_audio" playBeep="false" recordingStatusCallback="/process_audio"/></Response>',
        to=request.form["to"],
        from_=os.getenv("TWILIO_PHONE_NUMBER")
    )
    

    return redirect(url_for("success"))  # Redirect to a success page

# This is where Twilio posts the recorded audio
@app.route("/process_audio", methods=["POST"])
def process_audio():
    recording_url = request.form["RecordingUrl"] + ".mp3"
    audio_file = requests.get(recording_url)

    # Send to Deepgram
    deepgram_response = requests.post(
        "https://api.deepgram.com/v1/listen",
        headers={"Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}"},
        data=audio_file.content
    )
    text = deepgram_response.json()["results"]["channels"][0]["alternatives"][0]["transcript"]

    # Send to GPT via Groq with a system prompt
    gpt_response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
            "Content-Type": "application/json"
        },
        json={
            "model": "mixtral-8x7b-32768",
            "messages": [
                {
                    "role": "system",
                    "content": '''You are a polite and professional female HR representative. Your job is to call candidates to inform them about their selection for the second round of interviews and to schedule their next interview.

Conversation Flow:

1. Start by greeting the candidate and confirming their name.
2. Once confirmed, say something like:
"I'm pleased to inform you that you've been selected for Round 2 of the interview process. Congratulations!"
3. Inform them that the next interview is scheduled for the 2nd week of June.
4. Ask if they are available at that time so that the appointment can be confirmed.
5. If the user says they are not available or wants to shift the date:
Politely say: "Let me check the available slots for you."
Offer an alternative: 4th week of June.
6. If they accept, ask for confirmation and proceed to confirm the appointment.
7. If they still have a problem:
Say: "Unfortunately, no more options are available at this time. Could you please let me know which week would work best for you?"
Once they provide a week, confirm it and finalize the appointment.
8. End the call by thanking the candidate.

Tone: Friendly, formal, and efficient. Prioritize clear communication and a smooth user experience.'''
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
        }
    )
    reply_text = gpt_response.json()["choices"][0]["message"]["content"]

    # Convert reply to voice with ElevenLabs
    tts_response = requests.post(
        "https://api.elevenlabs.io/v1/text-to-speech/90ipbRoKi4CpHXvKVtl0/stream",
        headers={
            "xi-api-key": os.getenv("ELEVEN_API_KEY"),
            "Content-Type": "application/json"
        },
        json={"text": reply_text}
    )

    with open(REPLY_AUDIO_PATH, "wb") as f:
        f.write(tts_response.content)

    # Respond TwiML to play generated audio and record user again
    response = VoiceResponse()
    response.play(f"https://ai-voice-bot-production-1ecc.up.railway.app/static/response.mp3")
    response.record(max_length="10", action="/process_audio", play_beep=False)

    return Response(str(response), mimetype="text/xml")

# Serve static files like welcome.mp3 or response.mp3
@app.route("/static/<path:path>")
def send_static(path):
    return send_file(f"static/{path}")

@app.route("/success")
def success():
    return render_template("success.html")  # Create this file next

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
