"""
Main application entry point.
Runs both the Plivo XML server and the Slack bot.
"""

import os
import threading
from flask import Flask, Response
from dotenv import load_dotenv
from plivo import plivoxml

from message_parser import TemperatureAction
from phone_caller import PhoneCaller, get_tts_message
from slack_bot import TemperatureBot

# Load environment variables
load_dotenv()

# Flask app for serving Plivo XML
flask_app = Flask(__name__)


@flask_app.route("/plivo-xml/<action>", methods=["GET", "POST"])
def plivo_xml(action):
    """
    Serve Plivo XML for text-to-speech based on the action.

    Args:
        action: 'increase' or 'decrease'
    """
    try:
        temp_action = TemperatureAction(action)
    except ValueError:
        temp_action = TemperatureAction.NONE

    tts_message = get_tts_message(temp_action)

    if not tts_message:
        tts_message = "Hello, this is an automated call from your office regarding temperature control."

    # Create Plivo XML response
    response = plivoxml.ResponseElement()
    response.add(
        plivoxml.SpeakElement(tts_message, voice="WOMAN", language="en-US")
    )

    return Response(response.to_string(), mimetype="application/xml")


@flask_app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return {"status": "healthy"}


def run_flask():
    """Run the Flask server."""
    flask_app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)


def run_slack_bot(ngrok_url: str):
    """Run the Slack bot."""
    phone_caller = PhoneCaller(answer_url_base=ngrok_url)
    bot = TemperatureBot(phone_caller)
    bot.start()


def main():
    """Main entry point."""
    print("=" * 60)
    print("Temperature Control Automation")
    print("=" * 60)

    # Check for required environment variables
    required_vars = [
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
        "PLIVO_AUTH_ID",
        "PLIVO_AUTH_TOKEN",
        "PLIVO_PHONE_NUMBER",
        "TARGET_PHONE_NUMBER",
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"ERROR: Missing environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file.")
        return

    # Get the ngrok URL for Plivo callbacks
    ngrok_url = os.getenv("NGROK_URL")

    if not ngrok_url:
        print("\n" + "=" * 60)
        print("IMPORTANT: ngrok URL required!")
        print("=" * 60)
        print("\nPlivo needs a public URL to send call instructions.")
        print("\nSteps to set up:")
        print("1. In a separate terminal, run: ngrok http 5001")
        print("2. Copy the 'Forwarding' URL (e.g., https://abc123.ngrok.io)")
        print("3. Add it to your .env file: NGROK_URL=https://abc123.ngrok.io")
        print("4. Restart this application")
        print("\nAlternatively, enter the ngrok URL now:")

        ngrok_url = input("ngrok URL: ").strip()
        if not ngrok_url:
            print("No URL provided. Exiting.")
            return

    print(f"\nUsing ngrok URL: {ngrok_url}")
    print(f"Plivo XML endpoint: {ngrok_url}/plivo-xml/<action>")
    print(f"Target phone: {os.getenv('TARGET_PHONE_NUMBER')}")
    print(f"Monitoring channel: #{os.getenv('SLACK_CHANNEL', 'plivo_sports_updates')}")
    print("\n" + "=" * 60)

    # Start Flask server in a separate thread
    print("Starting Plivo XML server on port 8080...")
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start the Slack bot (this will block)
    print("Starting Slack bot...")
    run_slack_bot(ngrok_url)


if __name__ == "__main__":
    main()
