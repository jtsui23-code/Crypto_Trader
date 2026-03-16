import asyncio
import json
from pathlib import Path
from solana.rpc.websocket_api import connect
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.pubkey import Pubkey
from trader.engine.decoder import Decoder


"""
Class Name:
    WhaleListener

Description:
    Establishes a WebSocket connection to the Solana RPC endpoint
    and listens for real-time transaction log activity from a list
    of target whale wallet addresses loaded from a JSON file.

Member Variables:
    rpc_url (str):
        WebSocket RPC endpoint for Solana mainnet-beta.
    targets (list):
        List of whale wallet objects or addresses loaded from whales.json.
"""
class WhaleListener:
    """
    Method Name:
        __init__

    Parameters:
        rpc_url (str):
            WebSocket RPC endpoint URL.
            Defaults to Solana mainnet-beta public endpoint.

    Return:
        None

    Method Description:
        Initializes the WhaleListener by setting the RPC URL
        and loading the whale wallet targets from the JSON file.
    """
    def __init__(self, rpc_url="wss://api.mainnet-beta.solana.com"):
        self.rpc_url = rpc_url
        self.targets = self._load_targets()
        self.decoder = Decoder()


    """
    Method Name:
        _load_targets

    Parameters:
        None

    Return:
        list:
            A list of whale wallet objects or wallet address strings.
            Returns an empty list if the file does not exist or is invalid.

    Method Description:
        Loads whale wallet data from data/whales.json.
        Handles both:
            - A direct list of wallet objects
            - A dictionary containing a "wallets" key
        Validates that the final structure is a list.
        Gracefully handles file errors and malformed JSON.
    """
    def _load_targets(self):
        base_path = Path(__file__).parent.parent
        file_path = base_path / "data" / "whales.json" 

        try:
            if file_path.exists():
                with open(file_path, 'r') as f:
                    data = json.load(f)

                    if isinstance(data, dict) and "wallets" in data:
                        data = data["wallets"]
                    
                    if not isinstance(data, list):
                        print(f"Error: Expected list in {file_path.name}, got {type(data)}")
                        return []

                    return data
            else:
                print(f"Warning: {file_path} not found.")
                return []

        except Exception as e:
            print(f"Error reading JSON: {e}")
            return []


    """
    Method Name:
        start

    Parameters:
        None

    Return:
        None

    Method Description:
        Establishes an asynchronous WebSocket connection to the
        Solana RPC endpoint and subscribes to transaction logs
        for each whale wallet address.

        For each target:
            - Extracts wallet address and optional tag
            - Subscribes to transaction log mentions
            - Prints confirmation of subscription

        Continuously listens for incoming WebSocket messages
        and forwards them to process_message() for handling.
    """
    async def start(self):
        if not self.targets:
            print("No target whales found. Exiting.")
            return

        async with connect(self.rpc_url) as websocket:
            for target in self.targets:

                if isinstance(target, dict):
                    address = target.get('address')
                    tag = target.get('tag', 'Unknown')
                else:
                    address = target
                    tag = f"Whale_{address[:4]}"

                if not address:
                    continue

                await websocket.logs_subscribe(
                    filter_=RpcTransactionLogsFilterMentions(
                        Pubkey.from_string(address)
                    )
                )

                print(f"Subscribed to {tag}: {address}")

            print(f"Monitoring {len(self.targets)} whales for real-time activity...")

            async for msg in websocket:
                await self.process_message(msg)


    """
    Method Name:
        process_message

    Parameters:
        msg:
            Incoming WebSocket message containing transaction log data.

    Return:
        None

    Method Description:
        Processes incoming WebSocket messages after subscription.

        - Ignores initial subscription confirmation responses.
        - Extracts the transaction signature from detected activity.
        - Prints detected whale transaction signature.
        - Designed to later integrate with decoder.py for
          transaction decoding and trade logic execution.
    """
    async def process_message(self, msg):
        if not hasattr(msg[0], 'params'):
            return 

        try:
            signature = msg[0].params.result.value.signature
            print(f"Activity Detected! Signature: {signature}")

            await asyncio.to_thread(self.decoder.decode_swap, signature)

        except Exception as e:
            print(f"Error processing activity: {e}")


"""
Script Entry Point:

Initializes the WhaleListener class and starts the asynchronous
WebSocket listener. Gracefully handles manual interruption
(Ctrl + C) to stop the listener.
"""
if __name__ == "__main__":
    listener = WhaleListener()

    try:
        asyncio.run(listener.start())
    except KeyboardInterrupt:
        print("\nListener stopped.")