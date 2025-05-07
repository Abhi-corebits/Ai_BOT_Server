from flask import Flask, request, render_template
from twilio.rest import Client
import os

app = Flask(__name__)

# === Load Environment Variables ===
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
ELEVEN_AGENT_URL = os.environ.get("ELEVEN_AGENT_URL")  # This replaces TWIML_BIN_URL

# === Initialize Twilio Client ===
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# === Homepage with a form ===
@app.route("/")
def index():
    return render_template("index.html")  # HTML form to enter phone number

# === Route to trigger the call ===
@app.route("/call", methods=["POST"])
def call():
    to_number = request.form["to"]
    
    call = client.calls.create(
        to=to_number,
        from_=TWILIO_PHONE_NUMBER,
        url=ELEVEN_AGENT_URL  # Direct link to ElevenLabs' Listen & Reply agent
    )

    return f"Calling {to_number}..."

# === Start the server ===
if __name__ == "__main__":
    app.run(debug=True)
