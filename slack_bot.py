"""
Slack bot module for monitoring temperature requests.
"""

import os
import sys
import logging
import time
import threading
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from message_parser import parse_temperature_request, TemperatureAction, get_action_description
from phone_caller import PhoneCaller

# Rate limiting: only allow one call every 1 minute (60 seconds)
CALL_COOLDOWN_SECONDS = 1 * 60

# Polling configuration
POLL_DURATION_SECONDS = 60  # 1 minute
POLL_EMOJI_AGREE = "+1"      # 👍
POLL_EMOJI_DISAGREE = "-1"   # 👎

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
        self.active_poll = None  # Track if there's an active poll
        print(f"[RATE_LIMIT] Loaded last call time: {self.last_call_time}", flush=True)

        print(f"[INIT] Initializing Slack app...", flush=True)

        # Initialize Slack app with bot token
        self.app = App(token=os.getenv("SLACK_BOT_TOKEN"))

        print(f"[INIT] Slack app initialized. Registering handlers...", flush=True)

        # Register message handler
        self._register_handlers()

        print(f"[INIT] Handlers registered.", flush=True)

    def _start_poll(self, channel: str, action: TemperatureAction, requester: str):
        """Start a temperature poll in the channel."""
        if action == TemperatureAction.DECREASE:
            action_hint = "(make it cooler)"
        else:
            action_hint = "(make it warmer)"

        poll_message = (
            f"🌡️ *Wish to change temperature? {action_hint}*\n\n"
            f"Please vote:\n"
            f"• 👍 - Yes\n"
            f"• 👎 - No\n\n"
            f"_Poll ends in {POLL_DURATION_SECONDS} seconds. Action will be taken if majority agrees._"
        )

        # Post the poll message
        result = self.app.client.chat_postMessage(channel=channel, text=poll_message)
        poll_ts = result["ts"]

        # Add reaction emojis to the message
        self.app.client.reactions_add(channel=channel, timestamp=poll_ts, name=POLL_EMOJI_AGREE)
        self.app.client.reactions_add(channel=channel, timestamp=poll_ts, name=POLL_EMOJI_DISAGREE)

        print(f"[POLL] Started poll in channel {channel}, message ts: {poll_ts}", flush=True)

        # Store active poll info
        self.active_poll = {
            "channel": channel,
            "ts": poll_ts,
            "action": action,
            "requester": requester
        }

        # Schedule poll completion
        timer = threading.Timer(POLL_DURATION_SECONDS, self._complete_poll, args=[channel, poll_ts, action])
        timer.start()

    def _complete_poll(self, channel: str, poll_ts: str, action: TemperatureAction):
        """Complete the poll and take action based on results."""
        print(f"[POLL] Completing poll {poll_ts}", flush=True)

        try:
            # Get reactions on the poll message
            result = self.app.client.reactions_get(channel=channel, timestamp=poll_ts)
            reactions = result.get("message", {}).get("reactions", [])

            agree_count = 0
            disagree_count = 0

            for reaction in reactions:
                if reaction["name"] == POLL_EMOJI_AGREE:
                    # Subtract 1 because bot adds the initial reaction
                    agree_count = reaction["count"] - 1
                elif reaction["name"] == POLL_EMOJI_DISAGREE:
                    disagree_count = reaction["count"] - 1

            total_votes = agree_count + disagree_count
            print(f"[POLL] Results - Agree: {agree_count}, Disagree: {disagree_count}, Total: {total_votes}", flush=True)

            # Check for simple majority
            if total_votes == 0:
                self.app.client.chat_postMessage(
                    channel=channel,
                    text="⏱️ Poll ended with no votes. No action will be taken."
                )
            elif agree_count > disagree_count:
                # Majority agrees - make the call
                self._execute_temperature_action(channel, action, agree_count, disagree_count)
            else:
                # Majority disagrees or tie
                self.app.client.chat_postMessage(
                    channel=channel,
                    text=f"⏱️ Poll ended. Majority did not agree ({agree_count} yes, {disagree_count} no). No action will be taken."
                )

        except Exception as e:
            print(f"[POLL] Error completing poll: {e}", flush=True)
            self.app.client.chat_postMessage(
                channel=channel,
                text=f"❌ Error processing poll results: {str(e)}"
            )
        finally:
            self.active_poll = None

    def _execute_temperature_action(self, channel: str, action: TemperatureAction, agree: int, disagree: int):
        """Execute the temperature change after poll approval."""
        print(f"[CALL] Poll passed - initiating phone call...", flush=True)

        result = self.phone_caller.make_temperature_call(action)
        print(f"[CALL] Result: {result}", flush=True)

        if result["success"]:
            current_time = time.time()
            self.last_call_time = current_time
            save_last_call_time(current_time)
            action_desc = get_action_description(action)
            self.app.client.chat_postMessage(
                channel=channel,
                text=f"✅ Poll passed ({agree} yes, {disagree} no)! Calling facilities to {action_desc}."
            )
            print(f"[CALL] Success - posted confirmation to Slack", flush=True)
        else:
            self.app.client.chat_postMessage(
                channel=channel,
                text=f"⏱️ Poll passed ({agree} yes, {disagree} no), but couldn't place the call. Error: {result.get('error', 'Unknown error')}"
            )
            print(f"[CALL] Failed: {result.get('error')}", flush=True)

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

                # Check if there's already an active poll
                if self.active_poll is not None:
                    print(f"[POLL] Poll already active, ignoring new request", flush=True)
                    say(f"A temperature poll is already in progress. Please vote on the existing poll!")
                    return

                # Start a poll instead of making an immediate call
                print(f"[POLL] Starting temperature poll...", flush=True)
                self._start_poll(channel, action, user)

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
