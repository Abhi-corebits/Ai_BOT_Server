from flask import Flask, request, render_template
from twilio.rest import Client
import os

app = Flask(__name__)

# === Load from environment ===
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
TWIML_BIN_URL = os.environ.get("TWIML_BIN_URL")  # URL of your TwiML Bin

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/call", methods=["POST"])
def call():
    to_number = request.form["to"]
    
    call = client.calls.create(
        to=to_number,
        from_=TWILIO_PHONE_NUMBER,
        url=TWIML_BIN_URL  # Will stream to ElevenLabs agent
    )

    return f"Calling {to_number}..."

if __name__ == "__main__":
    app.run(debug=True)
