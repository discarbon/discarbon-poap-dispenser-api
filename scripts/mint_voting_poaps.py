# requires "pip install -e ." in base directory
import importlib
import logging
import os

import yaml
from dotenv import load_dotenv
from web3 import Web3

import app.wen_poap as wen_poap

importlib.reload(logging)  # prevent duplicate lines in ipython

load_dotenv()

# test config
# event_id_whitelist = 71182
# address_whitelist_txt = "./address_list_test_poap.txt"

# voter config
event_id_whitelist = 79416
address_whitelist_txt = "./address_list_contributed_and_voted.txt"

wen_poap_config_yml = "../config.yaml"


class WhitelistedEvent(wen_poap.EventABC):
    def __init__(self, *args, config=None):
        super().__init__(*args)

    def is_eligible(self, to_address):
        """
        Check whether an address is eligible for the POAP.
        """
        return True


if __name__ == "__main__":

    logFormatter = logging.Formatter(
        "%(asctime)s [%(levelname)-5.5s]  %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)

    fileHandler = logging.FileHandler(f"{os.path.splitext(address_whitelist_txt)[0]}.log")
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    # Load addresses
    with open(address_whitelist_txt, "r") as f:
        addresses = f.read().splitlines()

    # addresses = addresses[0:2]
    assert all([Web3.isAddress(address) for address in addresses]), "invalid address in whitelist"
    addresses = [Web3.toChecksumAddress(address) for address in addresses]
    logging.info(
        f"Will mint POAPs for event {event_id_whitelist} "
        f"(https://poap.gallery/r/event/{event_id_whitelist})..."
    )
    logging.info(f"...to {len(addresses)} addresses.")
    for address in addresses:
        logging.info(address)
    input("Press any key to continue...")

    # Load POAP API credentials from the environment
    api_key = os.environ.get("API_KEY")
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    audience = os.environ.get("AUDIENCE")
    assert all([api_key, client_id, client_secret, audience]), "not all required env vars set"

    # Initialize API wrapper; get oauth token
    poap_api = wen_poap.PoapApiWrapper(
        "https://api.poap.tech/", audience, api_key, client_id, client_secret
    )

    # Load configured events
    with open(wen_poap_config_yml, "r") as file:
        config = yaml.safe_load(file)

    # Get event secrets and initialize event
    event = None
    for event_config in config["discarbon_poap_dispenser_api"]["events"]:
        event_id = event_config["id"]
        event_secret = os.environ.get(f"SECRET_EVENT_{event_id}")
        if event_id == event_id_whitelist:
            event = WhitelistedEvent(poap_api, event_id, event_secret, config=event_config)

    assert event, f"Didn't find event {event_id_whitelist} in {wen_poap_config_yml}"

    # Mint POAPs
    for index, address in enumerate(addresses):
        try:
            response = event.mint_poap(address)
        except Exception as e:
            logging.error(f"{index} {address}: exception {e}")
            continue
        if response["success"]:
            logging.info(f"{index} {address}: success: https://app.poap.xyz/scan/{address}")
        else:
            logging.error(f"{index} {address}: {response['message']}")
