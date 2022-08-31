import json
import os
from textwrap import dedent

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from uvicorn.workers import UvicornWorker
from web3 import Web3

import app.wen_poap as wen_poap

load_dotenv()


class PoapApiUvicornWorker(UvicornWorker):
    CONFIG_KWARGS = {
        "log_config": "logging.yaml",
    }


description = dedent(
    """disCarbon's POAP Dispenser API.
       Accepts requests to mint POAPs for eligible addresses.
    """
)

tags_metadata = [
    {"name": "Auxiliary", "description": "Auxiliary endpoints"},
    {
        "name": "POAP Minting",
        "description": "Mint POAPs to addresses",
    },
]

poap_api = FastAPI(
    title="disCarbon POAP Dispenser API",
    description=description,
    contact={
        "name": "dan",
        "email": "danceratopz@gmail.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    openapi_tags=tags_metadata,
)


def load_abi(filename):
    with open(filename, "r") as f:
        abi = json.load(f)
    return abi


class DevconEvent(wen_poap.EventABC):
    def __init__(self, *args, config=None):
        super().__init__(*args)

        rpc_url = os.environ.get(f"RPC_URL_{config['id']}")
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))

        # block_number = self.web3.eth.blockNumber
        # print(f"Connected: {self.web3.isConnected()}, block number: {block_number}")
        if not self.web3.isConnected():
            raise Exception("Failed to connect to Polygon RPC; unable to check eligibility")
        self.contract_address = config["eligibility"]["contract_address"]
        abi_filename = config["eligibility"]["contract_abi_filename"]
        self.min_nct_contribution = config["eligibility"]["min_nct_contribution"]
        abi = load_abi(abi_filename)
        self.pooling_contract = self.web3.eth.contract(address=self.contract_address, abi=abi)

    def is_eligible(self, to_address):
        """
        Check whether an address is eligible for the POAP.
        """
        nct_amount_wei = self.pooling_contract.functions.contributions(to_address).call()
        nct_amount = Web3.fromWei(nct_amount_wei, "ether")
        if nct_amount >= self.min_nct_contribution:
            return True
        else:
            return False


events = {}


@poap_api.on_event("startup")
async def startup_event():

    # Load POAP API credentials from the environment
    api_key = os.environ.get("API_KEY")
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    audience = os.environ.get("AUDIENCE")

    # TODO: check values are not none.

    # Initialize API wrapper; currently assumed constant for all events
    poap_api = wen_poap.PoapApiWrapper(
        "https://api.poap.tech/", audience, api_key, client_id, client_secret
    )
    # Load configured events
    with open("config.yaml", "r") as file:
        config = yaml.safe_load(file)

    # Initialize configured events
    for event_config in config["discarbon_poap_dispenser_api"]["events"]:
        event_id = event_config["id"]
        event_secret = os.environ.get(f"SECRET_EVENT_{event_id}")
        if event_id == 45486:
            events[event_id] = DevconEvent(poap_api, event_id, event_secret, config=event_config)


@poap_api.get("/", tags=["Auxiliary"])
async def root():
    """
    Return a helpful docstring pointing to the API's Swagger documentation if no
    valid endpoint is provided.
    """
    return {
        "message": (
            """Welcome to the disCarbon POAP Dispenser API. Documentation is """
            """available at https://poap.discarbon.earth/docs"""
        )
    }


# If we have dependencies on other services, consider https://github.com/Kludex/fastapi-health
@poap_api.get("/health", tags=["Auxiliary"])
async def app_health():
    """
    Basic health check to verify the API is still running.
    """
    return {"alive": True}


@poap_api.get("/isEligible/{event_id}/{to_address}")
async def is_eligible(
    event_id: int,
    to_address: str,
):
    """
    Return true if to_address is eligible to receive the POAP for event_id,
    false otherwise
    """
    if event_id not in events.keys():
        return {"success": False, "message": f"error: event with id {event_id} is not configured"}
    if not Web3.isAddress(to_address):
        # TODO: allow ENS domain names (isAddress() only checks standard address formats
        return {
            "success": False,
            "message": f"error: invalid Ethereum address {to_address} "
            "(ENS domain names not currently supported)",
        }
    is_eligible = events[event_id].is_eligible(to_address)
    return {
        "success": True,
        "is_eligible": is_eligible,
        "address": to_address,
        "event_id": event_id,
        "message": f"address {to_address} is eligible for poap drop {event_id}",
    }


@poap_api.get(
    "/mint/{event_id}/{to_address}",
    tags=["POAP Minting"],
)
async def mint_poap(
    event_id: int,
    to_address: str,
):
    """
    Mint a POAP from event specified by mint_id to to_address, if eligible.
    """
    if event_id not in events.keys():
        return {"success": False, "message": f"error: event with id {event_id} is not configured"}
    if not Web3.isAddress(to_address):
        # TODO: allow ENS domain names (isAddress() only checks standard address formats
        return {
            "success": False,
            "message": f"error: invalid Ethereum address {to_address} "
            "(ENS domain names not currently supported)",
        }
    try:
        response = events[event_id].mint_poap(to_address)
    except Exception as e:
        return {"success": False, "message": e}
    if ("statusCode" in response.content) and (response.content["statusCode"] != 200):
        response.content["success"] = False
        return json.dumps(response.content)
    response.content["success"] = True
    return json.dumps(response.content)


@poap_api.get(
    "/getMintStatus/{event_id}/{uuid}",
    tags=["POAP Minting"],
)
async def get_mint_status(
    event_id: int,
    uuid: str,
):
    """
    Get the current minting status.

    Comment: poap api return status code upon invalid uuid, but not if the uuid is valid.
    """
    try:
        content = events[event_id].get_mint_status(uuid)
    except Exception as e:
        return {"success": False, "message": e}
    if ("statusCode" in content) and (content["statusCode"] != 200):
        content["success"] = False
        return content
    operation = content["operation"]
    if operation != "mintToken":
        return {"success": False, "message": f'uid operation ({operation}) is not "mintToken"'}
    return {
        "success": True,
        "uid": uuid,
        "mint_status": content["status"],
        "tx_hash": content["result"]["tx_hash"],
    }
