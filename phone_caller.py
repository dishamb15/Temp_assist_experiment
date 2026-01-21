"""
Phone caller module using Plivo for automated calls with text-to-speech.
"""

import os
import plivo
from message_parser import TemperatureAction


class PhoneCaller:
    def __init__(self, answer_url_base: str):
        """
        Initialize the phone caller.

        Args:
            answer_url_base: Base URL where Plivo XML is served (e.g., ngrok URL)
        """
        self.auth_id = os.getenv("PLIVO_AUTH_ID")
        self.auth_token = os.getenv("PLIVO_AUTH_TOKEN")
        self.from_number = os.getenv("PLIVO_PHONE_NUMBER")
        self.target_number = os.getenv("TARGET_PHONE_NUMBER")

        if not all([self.auth_id, self.auth_token, self.from_number, self.target_number]):
            raise ValueError("Missing Plivo credentials in environment variables")

        self.client = plivo.RestClient(self.auth_id, self.auth_token)
        self.answer_url_base = answer_url_base

    def make_temperature_call(self, action: TemperatureAction) -> dict:
        """
        Make a phone call with a temperature adjustment request.

        Args:
            action: The temperature action (INCREASE or DECREASE)

        Returns:
            dict with call status information
        """
        if action == TemperatureAction.NONE:
            return {"success": False, "error": "No action required"}

        try:
            answer_url = f"{self.answer_url_base}/plivo-xml/{action.value}"

            response = self.client.calls.create(
                from_=self.from_number,
                to_=self.target_number,
                answer_url=answer_url,
                answer_method="GET",
            )

            return {
                "success": True,
                "call_uuid": response.request_uuid,
                "message": f"Call initiated to {self.target_number}",
                "action": action.value
            }
        except plivo.exceptions.PlivoRestError as e:
            return {
                "success": False,
                "error": str(e)
            }


def get_tts_message(action: TemperatureAction) -> str:
    """Generate the text-to-speech message based on the action."""
    if action == TemperatureAction.INCREASE:
        return (
            "Hi, this is an automated call from Plivo. "
            "The employees have reported that the temperature is too cold. "
            "Please increase the AC temperature. "
            "Thank you."
        )
    elif action == TemperatureAction.DECREASE:
        return (
            "Hi, this is an automated call from Plivo. "
            "The employees have reported that the temperature is too hot. "
            "Please reduce the AC temperature. "
            "Thank you."
        )
    return ""
