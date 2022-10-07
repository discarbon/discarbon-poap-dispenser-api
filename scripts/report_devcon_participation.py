import json

from web3 import Web3


def load_abi(filename):
    with open(filename, "r") as f:
        abi = json.load(f)
    return abi


rpc_url = "https://poly-rpc.gateway.pokt.network/"
web3 = Web3(Web3.HTTPProvider(rpc_url))
block_number = web3.eth.blockNumber
print(f"Connected: {web3.isConnected()}, block number: {block_number}")

contract_address = Web3.toChecksumAddress("0xb6A5D547d0A325Ffa0357E2698eB76E165b606BA")
abi_filename = (
    "../resources/71937/Devcon_Offset_Pool_0xb6A5D547d0A325Ffa0357E2698eB76E165b606BA.json"
)

abi = load_abi(abi_filename)
pooling_contract = web3.eth.contract(address=contract_address, abi=abi)

contributor_addresses = pooling_contract.functions.getContributorsAddresses().call()
contributed_nct = pooling_contract.functions.totalCarbonPooled().call()

print("Contributor count: ", len(contributor_addresses))
print("Amount of NCT contributed:", web3.fromWei(contributed_nct, "ether"))
