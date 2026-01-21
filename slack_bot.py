"""
Slack bot module for monitoring temperature requests.
"""

import os
import sys
import logging
import time
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from message_parser import parse_temperature_request, TemperatureAction, get_action_description
from phone_caller import PhoneCaller

# Rate limiting: only allow one call every 30 minutes (1800 seconds)
CALL_COOLDOWN_SECONDS = 30 * 60

# File to persist last call time across restarts
LAST_CALL_FILE = os.path.join(os.path.dirname(__file__), ".last_call_time")

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def load_last_call_time() -> float:
    """Load the last call time from file."""
    try:
        if os.path.exists(LAST_CALL_FILE):
            with open(LAST_CALL_FILE, 'r') as f:
                return float(f.read().strip())
    except (ValueError, IOError) as e:
        print(f"[RATE_LIMIT] Could not load last call time: {e}", flush=True)
    return 0


def save_last_call_time(timestamp: float):
    """Save the last call time to file."""
    try:
        with open(LAST_CALL_FILE, 'w') as f:
            f.write(str(timestamp))
        print(f"[RATE_LIMIT] Saved last call time to file", flush=True)
    except IOError as e:
        print(f"[RATE_LIMIT] Could not save last call time: {e}", flush=True)


class TemperatureBot:
    def __init__(self, phone_caller: PhoneCaller):
        """
        Initialize the temperature monitoring Slack bot.

        Args:
            phone_caller: PhoneCaller instance for making calls
        """
        self.phone_caller = phone_caller
        self.channel_name = os.getenv("SLACK_CHANNEL", "plivo_sports_updates")
        self.last_call_time = load_last_call_time()  # Load from file to survive restarts
        print(f"[RATE_LIMIT] Loaded last call time: {self.last_call_time}", flush=True)

        print(f"[INIT] Initializing Slack app...", flush=True)

        # Initialize Slack app with bot token
        self.app = App(token=os.getenv("SLACK_BOT_TOKEN"))

        print(f"[INIT] Slack app initialized. Registering handlers...", flush=True)

        # Register message handler
        self._register_handlers()

        print(f"[INIT] Handlers registered.", flush=True)

    def _register_handlers(self):
        """Register event handlers for the Slack app."""

        @self.app.event("message")
        def handle_message(event, say, logger):
            """Handle incoming messages in channels."""
            print(f"[MESSAGE] Received event: {event}", flush=True)

            # Ignore bot messages and message edits
            if event.get("subtype"):
                print(f"[MESSAGE] Ignoring message with subtype: {event.get('subtype')}", flush=True)
                return

            text = event.get("text", "")
            channel = event.get("channel")
            user = event.get("user")

            print(f"[MESSAGE] From user {user} in channel {channel}: {text}", flush=True)

            # Parse the message for temperature requests
            action = parse_temperature_request(text)
            print(f"[MESSAGE] Parsed action: {action}", flush=True)

            if action != TemperatureAction.NONE:
                print(f"[ACTION] Temperature action detected: {action.value}", flush=True)

                # Check rate limiting
                current_time = time.time()
                time_since_last_call = current_time - self.last_call_time

                if time_since_last_call < CALL_COOLDOWN_SECONDS:
                    remaining_minutes = int((CALL_COOLDOWN_SECONDS - time_since_last_call) / 60)
                    print(f"[RATE_LIMIT] Call skipped - cooldown active. {remaining_minutes} minutes remaining.", flush=True)
                    say(
                        f"I noticed the temperature request, but a call was already made recently. "
                        f"To avoid duplicate calls, please wait {remaining_minutes} more minutes before the next call can be placed."
                    )
                    return

                # Make the phone call
                print(f"[CALL] Initiating phone call...", flush=True)
                result = self.phone_caller.make_temperature_call(action)
                print(f"[CALL] Result: {result}", flush=True)

                if result["success"]:
                    self.last_call_time = current_time  # Update last call time
                    save_last_call_time(current_time)  # Persist to file
                    action_desc = get_action_description(action)
                    say(
                        f"Got it! I'm calling facilities to {action_desc}. "
                        f"Call initiated successfully."
                    )
                    print(f"[CALL] Success - posted confirmation to Slack", flush=True)
                else:
                    say(
                        f"I detected a temperature request, but couldn't place the call. "
                        f"Error: {result.get('error', 'Unknown error')}"
                    )
                    print(f"[CALL] Failed: {result.get('error')}", flush=True)

    def start(self):
        """Start the bot using Socket Mode."""
        app_token = os.getenv("SLACK_APP_TOKEN")
        if not app_token:
            raise ValueError("SLACK_APP_TOKEN is required for Socket Mode")

        print(f"[START] Creating SocketModeHandler...", flush=True)
        handler = SocketModeHandler(self.app, app_token)

        print(f"", flush=True)
        print(f"=" * 50, flush=True)
        print(f"Temperature bot is running!", flush=True)
        print(f"Monitoring channel: #{self.channel_name}", flush=True)
        print(f"Waiting for temperature-related messages...", flush=True)
        print(f"=" * 50, flush=True)
        print(f"", flush=True)

        handler.start()
