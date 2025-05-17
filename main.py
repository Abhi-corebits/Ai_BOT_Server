from flask import Flask, request, send_file, Response, render_template, redirect, url_for
from twilio.twiml.voice_response import VoiceResponse
import requests
import os
import io
from dotenv import load_dotenv
from pydub import AudioSegment
from requests.auth import HTTPBasicAuth
from io import BytesIO

load_dotenv()

app = Flask(__name__)

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
    audio = AudioSegment.from_file(BytesIO(mp3_data), format="mp3")  # <-- specify format!
    wav_io = BytesIO()
    audio.export(wav_io, format="wav")
    wav_io.seek(0)
    return wav_io

@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        print("Received request at /process_audio")

        # 1. Append .mp3 and use auth
        recording_url = request.form["RecordingUrl"] + ".mp3"
        print(f"Recording URL: {recording_url}")

        # 2. Authenticated download from Twilio
        audio_file = requests.get(
            recording_url,
            auth=HTTPBasicAuth(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        )
        print("Downloaded audio")

        # 3. (Optional) Check content-type
        content_type = audio_file.headers.get("Content-Type", "")
        if "audio" not in content_type:
            print("Unexpected content type:", content_type)
            return "Invalid audio file", 400

        # 4. (Optional) Save audio for debugging
        with open("latest_recording.mp3", "wb") as debug_file:
            debug_file.write(audio_file.content)
            print("Saved downloaded audio for debugging")

        # 5. Convert MP3 to WAV
        wav_io = convert_mp3_to_wav(audio_file.content)
        print("Converted MP3 to WAV")

        # 6. Send to Deepgram
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

        # 7. Send to Groq (GPT)
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

Tone: Friendly, formal, and efficient. Prioritize clear communication and a smooth user experience.
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

        # 8. Convert reply to speech using ElevenLabs
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

        # 9. Respond with TwiML
        response = VoiceResponse()
        response.play("https://ai-voice-bot-production-1ecc.up.railway.app/static/response.mp3")
        response.record(max_length="10", action="/process_audio", play_beep=False)
        print("Responding with TwiML")

        return Response(str(response), mimetype="text/xml")

    except Exception as e:
        print("Error in /process_audio:", e)
        return Response("<Response><Say>Sorry, an error occurred.</Say></Response>", mimetype="text/xml")

@app.route("/static/<path:path>")
def send_static(path):
    return send_file(f"static/{path}")

@app.route("/success")
def success():
    return render_template("success.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
