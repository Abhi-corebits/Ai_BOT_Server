from flask import Flask, request, render_template
from twilio.rest import Client
import os

# Initialize the Flask app
app = Flask(__name__)

# === Step 1: Load Environment Variables ===
# These values should NOT be hardcoded — they are read from your Render Dashboard (or a .env file locally)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")  # Your Twilio number, like '+1415XXXXXXX'
TWIML_BIN_URL = os.environ.get("TWIML_BIN_URL")  # URL of the TwiML Bin you've created on Twilio

# === Step 2: Initialize the Twilio Client ===
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# === Step 3: Set up the homepage ===
@app.route("/")
def index():
    return render_template("index.html")  # A simple HTML form to input phone number

# === Step 4: Handle the call request ===
@app.route("/call", methods=["POST"])
def call():
    # Get the number entered by the user in the form
    to_number = request.form["to"]

    # Initiate a call using Twilio API
    call = client.calls.create(
        to=to_number,               # Number to call
        from_=TWILIO_PHONE_NUMBER,  # Your Twilio number
        url=TWIML_BIN_URL           # TwiML Bin URL that tells Twilio what to say/do
    )

    return f"Calling {to_number}..."

# === Step 5: Run the app ===
if __name__ == "__main__":
    app.run(debug=True)
