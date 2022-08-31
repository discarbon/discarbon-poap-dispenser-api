import json
import pickle
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

import requests


class PoapApiWrapper:
    oauth_token_filename = "./poap_oauth_token.pkl"

    def __init__(
        self,
        poap_api_endpoint: str,
        audience: str,
        api_key: str,
        client_id: str,
        client_secret: str,
    ):
        self.api_endpoint = poap_api_endpoint
        self.audience = audience
        self.api_key = api_key
        self.client_id = client_id
        self.client_secret = client_secret
        # Get and save oauth access token
        self.access_token = None
        self.access_token_expiry = datetime.now()
        self.load_oauth_token()
        if not self.access_token or self.has_oauth_token_expired():
            self.update_oauth_token()

    # TODO retry + exponential backoff with tenacity
    def update_oauth_token(self):
        """
        Request an OAuth token from POAP's oauth endpoint and store it
        for future use.
        """
        url = "https://poapauth.auth0.com/oauth/token"
        headers = {"Content-Type": "application/json"}
        data = {
            "audience": self.audience,
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        response = requests.request("POST", url, headers=headers, data=json.dumps(data))
        if not response.ok:
            print(
                f"Error requesting auth token ({response.status_code}), "
                f'reason: "{response.reason}"; text: "{response.text}"'
            )
            sys.exit(1)
        data = json.loads(response.content)
        self.access_token = data["access_token"]
        self.access_token_expiry = datetime.now() + timedelta(seconds=data["expires_in"] - 600)
        self.save_oauth_token()

    def has_oauth_token_expired(self):
        return datetime.now() >= self.access_token_expiry

    def save_oauth_token(self):
        """
        Save access token to disk to avoid getting rate limited by POAP's auth
        server. More relevant during testing than during production.
        """
        with open(self.oauth_token_filename, "wb") as f:
            pickle.dump([self.access_token, self.access_token_expiry], f)

    def load_oauth_token(self):
        try:
            with open(self.oauth_token_filename, "rb") as f:
                self.access_token, self.access_token_expiry = pickle.load(f)
            print("Successfully loaded oauth access token from file.")
        except Exception as e:
            print(f"Failed to load oauth access token from file: {e}")

    def get(self, route: str, protected: bool = True):
        if self.has_oauth_token_expired():
            self.update_oauth_token()
        url = f"{self.api_endpoint}{route}"
        headers = {
            "Accept": "application/json",
            "X-API-Key": self.api_key,
        }
        if protected:
            headers["Authorization"] = f"Bearer {self.access_token}"
        # Test/retry for bad response
        response = requests.get(url, headers=headers)
        return response

    def post(self, route: str, payload: dict, protected: bool = True):
        if self.has_oauth_token_expired():
            self.update_oauth_token()
        url = f"{self.api_endpoint}{route}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        if protected:
            headers["Authorization"] = f"Bearer {self.access_token}"
        # Test/retry for bad response
        response = requests.post(url, headers=headers, json=payload)
        return response


class EventABC(ABC):
    def __init__(self, poap_api: PoapApiWrapper, event_id: int, event_secret: str):
        self.poap_api = poap_api
        self.event_id = event_id
        self.event_secret = event_secret
        assert (
            self.is_valid_event()
        ), f"event/validate claims the event with id {event_id} is not valid."
        self.update_unclaimed_qr_codes()

    @abstractmethod
    def is_eligible(self, address: str) -> bool:
        """
        Check whether an address is eligible to receive a POAP for this event drop.

        This method must be implemented by the concrete class that inherits from
        EventABC.
        """
        pass

    def is_valid_event(self) -> bool:
        response = self.validate_event()
        is_valid = response["valid"]
        return is_valid

    def validate_event(self) -> dict:
        payload = {"event_id": self.event_id, "secret_code": self.event_secret}
        response = self.poap_api.post("event/validate", payload)
        return json.loads(response.content)

    def update_unclaimed_qr_codes(self) -> None:
        payload = {"secret_code": self.event_secret}
        response = self.poap_api.post(f"event/{self.event_id}/qr-codes", payload)
        qr_codes = json.loads(response.content)
        unclaimed_qr_codes = [qr["qr_hash"] for qr in qr_codes if qr["claimed"] is False]
        self.qr_codes = unclaimed_qr_codes

    def claim_qr_get_secret(self, qr_code: str) -> str:
        response = self.poap_api.get(f"actions/claim-qr?qr_hash={qr_code}")
        content = json.loads(response.content)
        assert not content["claimed"], "qr hash already claimed"
        assert int(content["event"]["id"]) == int(
            self.event_id
        ), f"Expected event id {self.event_id}, got {content['event']['id']}"
        # TODO: check current data not past expiry date.
        return content["secret"]

    def claim_qr(self, qr_code: str, qr_secret: str, to_address: str) -> dict:
        payload = {"address": to_address, "qr_hash": qr_code, "secret": qr_secret}
        response = self.poap_api.post("actions/claim-qr", payload)
        return json.loads(response.content)

    def mint_poap(self, to_address: str) -> dict:
        if not self.is_eligible(to_address):
            return {
                "message": f"the address {to_address} is not eligible for poap drop "
                f"{self.event_id}"
            }
        if not self.qr_codes:
            return {
                "message": "this event has no run out of claim codes, please inform the organizers"
            }
        qr_code = self.qr_codes.pop()
        qr_secret = self.claim_qr_get_secret(qr_code)
        response = self.claim_qr(qr_code, qr_secret, to_address)
        return response

    def get_mint_status(self, uid: str) -> dict:
        response = self.poap_api.get(f"queue-message/{uid}", protected=False)
        return json.loads(response.content)