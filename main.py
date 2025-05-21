from flask import Flask, request, send_file, Response, render_template, redirect, url_for
from twilio.twiml.voice_response import VoiceResponse
import requests
import os
import io
from dotenv import load_dotenv
from pydub import AudioSegment
from requests.auth import HTTPBasicAuth
from io import BytesIO
import subprocess 
import time
from flask import send_from_directory

load_dotenv()

app = Flask(__name__)

# Constants
BASE_URL = "https://ai-voice-bot-production-1ecc.up.railway.app"
WELCOME_MP3_URL = f"{BASE_URL}/static/welcome.mp3"
REPLY_AUDIO_PATH = "static/response.mp3"

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

# Function to re-encode MP3 in Twilio-friendly format
def reencode_mp3_for_twilio(input_file, output_file):
    command = [
        "ffmpeg",
        "-y",
        "-i", input_file,
        "-ar", "44100",     # Sample rate
        "-ac", "1",         # Mono
        "-b:a", "128k",     # Constant bitrate
        "-f", "mp3",        # MP3 format
        output_file
    ]
    subprocess.run(command, check=True)

@app.route("/call", methods=["POST"])
def start_call():
    from twilio.rest import Client
    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

    call = client.calls.create(
        twiml=f'''
        <Response>
            <Play>{WELCOME_MP3_URL}</Play>
            <Pause length="2"/>
            <Record 
                maxLength="7" 
                action="{BASE_URL}/process_audio"
                recordingStatusCallback="{BASE_URL}/process_audio"
                playBeep="false" 
            />
        </Response>
        ''',
        to=request.form["to"],
        from_=os.getenv("TWILIO_PHONE_NUMBER")
    )

    return redirect(url_for("success"))

# Convert MP3 to Deepgram-compatible WAV
def convert_mp3_to_wav(mp3_data):
    audio = AudioSegment.from_file(BytesIO(mp3_data), format="mp3")
    wav_io = BytesIO()
    audio.export(wav_io, format="wav")
    wav_io.seek(0)
    return wav_io

@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        print("Received request at /process_audio")

        recording_url = request.form["RecordingUrl"] + ".mp3"
        print(f"Recording URL: {recording_url}")

        # 2. Retry audio download from Twilio (wait if audio isn't ready yet)
        MAX_RETRIES = 5
        audio_file = None

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"Attempt {attempt}: Downloading audio...")
            response = requests.get(
                recording_url,
                auth=HTTPBasicAuth(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
            )
            content_type = response.headers.get("Content-Type", "")

            if "audio" in content_type:
                audio_file = response
                print("Audio file is ready and downloaded.")
                break
            else:
                print(f"Audio not ready yet (Content-Type: {content_type}). Retrying...")
                time.sleep(2)  # Wait 2 seconds before retrying

        if not audio_file:
            print("Failed to download audio after retries.")
            return Response("<Response><Say>Sorry, your recording is not available yet. Please try again later.</Say></Response>", mimetype="text/xml")

        with open("latest_recording.mp3", "wb") as debug_file:
            debug_file.write(audio_file.content)
            print("Saved downloaded audio for debugging")

        wav_io = convert_mp3_to_wav(audio_file.content)
        print("Converted MP3 to WAV")

        deepgram_response = requests.post(
            "https://api.deepgram.com/v1/listen",
            headers={
                "Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}",
                "Content-Type": "audio/wav"
            },
            data=wav_io.read()
        )
        print(f"Deepgram response: {deepgram_response.status_code}")
        print(deepgram_response.text)

        text = deepgram_response.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
        print(f"Transcript: {text}")

        gpt_response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-70b-8192",
                "messages": [
                    {"role": "system", "content": '''
You are job is to reply to every sentence, every question, every reply as - "Good Morning!" in a joyful tone.
you are only allowed to say good morning and nothing more than that , not even a single extra word rather than good morning.
'''},
                    {"role": "user", "content": text}
                ]
            }
        )

        print(f"Groq response: {gpt_response.status_code}")
        print(gpt_response.text)

        try:
            groq_json = gpt_response.json()
            print("Groq full JSON response:", groq_json)
            reply_text = groq_json["choices"][0]["message"]["content"]
            print(f"GPT Reply: {reply_text}")
        except Exception as e:
            print("Failed to parse Groq JSON response:", e)
            reply_text = "Sorry, there was an error with the AI response."

        tts_response = requests.post(
            "https://api.elevenlabs.io/v1/text-to-speech/90ipbRoKi4CpHXvKVtl0/stream",
            headers={
                "xi-api-key": os.getenv("ELEVEN_API_KEY"),
                "Content-Type": "application/json"
            },
            json={"text": reply_text}
        )
        print("Got TTS response from ElevenLabs")

        with open(REPLY_AUDIO_PATH, "wb") as f:
            f.write(tts_response.content)
        print("Saved response.mp3")

        reencode_mp3_for_twilio(REPLY_AUDIO_PATH, "static/twilio_ready.mp3")
        print("Re-encoded MP3 for Twilio")
        time.sleep(1)

        response = VoiceResponse()
        response.play(f"{BASE_URL}/static/twilio_ready.mp3")
        response.pause(length=1.5)
        response.record(
            max_length="7",
            action=f"{BASE_URL}/process_audio",
            recordingStatusCallback=f"{BASE_URL}/process_audio",
            play_beep=False
        )
        return Response(str(response), mimetype="application/xml")

    except Exception as e:
        print("Error in /process_audio:", e)
        return Response("<Response><Say>Sorry, an error occurred.</Say></Response>", mimetype="text/xml")

@app.route("/static/twilio_ready.mp3")
def serve_twilio_audio():
    return send_file("static/twilio_ready.mp3", mimetype="audio/mpeg")

@app.route("/static/<path:path>")
def send_static(path):
    return send_file(f"static/{path}")

@app.route("/success")
def success():
    return render_template("success.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
