from flask import Flask, request, Response

app = Flask(__name__)

@app.route("/")
def index():
    return "Flask server is running. Visit /voice to test Twilio XML."

@app.route("/voice", methods=["GET", "POST"])
def voice():
    response = """
    <Response>
        <Say voice="Polly.Joanna">Hello! This is your AI agent speaking.</Say>
    </Response>
    """
    return Response(response, mimetype="text/xml")

if __name__ == "__main__":
    app.run(debug=True)