from flask import Flask, request, send_file, Response, render_template, redirect, url_for
from twilio.twiml.voice_response import VoiceResponse
import requests
import os
import io
import time
import logging
from dotenv import load_dotenv
from pydub import AudioSegment
from requests.auth import HTTPBasicAuth
from io import BytesIO

# Load .env variables
load_dotenv()

# Setup Flask
app = Flask(__name__)

# Logging to file
logging.basicConfig(filename='app.log', level=logging.INFO)

# Constants
WELCOME_MP3_URL = "https://ai-voice-bot-production-1ecc.up.railway.app/static/welcome.mp3"
REPLY_AUDIO_PATH = "static/response.mp3"

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/call", methods=["POST"])
def start_call():
    from twilio.rest import Client
    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

    BASE_URL = "https://ai-voice-bot-production-1ecc.up.railway.app"

    call = client.calls.create(
        twiml=f'''
        <Response>
            <Play>{WELCOME_MP3_URL}</Play>
            <Pause length="2"/>
            <Record 
                maxLength="10" 
                action="{BASE_URL}/process_audio"
                playBeep="false" 
            />
        </Response>
        ''',
        to=request.form["to"],
        from_=os.getenv("TWILIO_PHONE_NUMBER")
    )

    return redirect(url_for("success"))

def convert_mp3_to_wav(mp3_data):
    audio = AudioSegment.from_file(BytesIO(mp3_data), format="mp3")
    wav_io = BytesIO()
    audio.export(wav_io, format="wav")
    wav_io.seek(0)
    return wav_io

@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        logging.info("Received request at /process_audio")

        # 1. Get recording URL
        recording_url = request.form["RecordingUrl"] + ".mp3"
        logging.info(f"Recording URL: {recording_url}")

        # 2. Download audio with auth
        audio_file = requests.get(
            recording_url,
            auth=HTTPBasicAuth(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        )

        # 3. Verify audio
        if "audio" not in audio_file.headers.get("Content-Type", ""):
            logging.error("Invalid content type from Twilio")
            return Response("<Response><Say>Invalid audio file.</Say></Response>", mimetype="text/xml")

        # 4. Save original recording
        with open("latest_recording.mp3", "wb") as debug_file:
            debug_file.write(audio_file.content)

        # 5. Convert MP3 to WAV
        wav_io = convert_mp3_to_wav(audio_file.content)

        # 6. Transcribe via Deepgram
        deepgram_response = requests.post(
            "https://api.deepgram.com/v1/listen",
            headers={
                "Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}",
                "Content-Type": "audio/wav"
            },
            data=wav_io.read()
        )

        if deepgram_response.status_code != 200:
            logging.error("Deepgram transcription failed")
            return Response("<Response><Say>Could not transcribe audio.</Say></Response>", mimetype="text/xml")

        text = deepgram_response.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
        logging.info(f"Transcript: {text}")

        # 7. Generate reply via Groq (GPT)
        gpt_response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "meta-llama/llama-guard-4-12b",
                "messages": [
                    {"role": "system", "content": '''
You are a polite and professional female HR representative. Your job is to call candidates to inform them about their selection for the second round of interviews and to schedule their next interview.

Conversation Flow:
1. Start by greeting the candidate and confirming their name.
2. Congratulate them on being selected for Round 2.
3. Mention that Round 2 is scheduled for the 2nd week of June.
4. Ask if they're available at that time.
5. If not, offer the 4th week of June.
6. If still not available, ask for their preferred week and confirm.
7. End by thanking them.

Tone: Friendly, formal, and efficient.
                    '''},
                    {"role": "user", "content": text}
                ]
            }
        )

        if gpt_response.status_code != 200:
            logging.error("Groq GPT API failed")
            return Response("<Response><Say>Could not generate a reply.</Say></Response>", mimetype="text/xml")

        reply_text = gpt_response.json()["choices"][0]["message"]["content"]
        logging.info(f"GPT Reply: {reply_text}")

        # 8. Convert reply to speech using ElevenLabs
        tts_response = requests.post(
            "https://api.elevenlabs.io/v1/text-to-speech/90ipbRoKi4CpHXvKVtl0/stream",
            headers={
                "xi-api-key": os.getenv("ELEVEN_API_KEY"),
                "Content-Type": "application/json"
            },
            json={"text": reply_text}
        )

        if tts_response.status_code != 200:
            logging.error("ElevenLabs TTS failed")
            return Response("<Response><Say>Could not convert reply to audio.</Say></Response>", mimetype="text/xml")

        # 9. Save generated audio
        with open(REPLY_AUDIO_PATH, "wb") as f:
            f.write(tts_response.content)
        time.sleep(0.5)

        # 10. Validate file
        if os.path.getsize(REPLY_AUDIO_PATH) < 1000:
            logging.error("TTS audio too small or corrupt")
            return Response("<Response><Say>Generated audio file was invalid.</Say></Response>", mimetype="text/xml")

        # 11. Respond with TwiML to play and loop
        response = VoiceResponse()
        response.play(url_for('send_static', path='response.mp3', _external=True))
        response.pause(length=1)
        response.record(max_length="10", action="/process_audio", play_beep=False)
        return Response(str(response), mimetype="text/xml")

    except Exception as e:
        logging.exception("Error in /process_audio")
        return Response("<Response><Say>Sorry, an error occurred.</Say></Response>", mimetype="text/xml")

@app.route("/static/<path:path>")
def send_static(path):
    return send_file(f"static/{path}", mimetype="audio/mpeg")

@app.route("/success")
def success():
    return render_template("success.html")

if __name__ == "__main__":
    app.debug = True
    port = int(os.environ.get("PORT", 8000))
    
    app.run(host="0.0.0.0", port=port)
