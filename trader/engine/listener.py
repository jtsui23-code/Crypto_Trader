import asyncio
import json
from pathlib import Path
from solana.rpc.websocket_api import connect
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.pubkey import Pubkey

class WhaleListener:
    def __init__(self, rpc_url="wss://api.mainnet-beta.solana.com"):
        self.rpc_url = rpc_url
        self.targets = self._load_targets()

    def _load_targets(self):
        """Loads target whales from JSON, ensuring we get a list of objects."""
        base_path = Path(__file__).parent.parent
        file_path = base_path / "data" / "whales.json" 

        try:
            if file_path.exists():
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    # If the JSON is wrapped in a "wallets" key, extract it
                    if isinstance(data, dict) and "wallets" in data:
                        data = data["wallets"]
                    
                    # Ensure data is a list
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

    async def start(self):
        """Starts the WebSocket connection and subscribes to whale logs ."""
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

                # Subscribe to account logs 
                await websocket.logs_subscribe(
                    filter_=RpcTransactionLogsFilterMentions(Pubkey.from_string(address))
                )
                print(f"Subscribed to {tag}: {address}")

            print(f"Monitoring {len(self.targets)} whales for real-time activity...")

            async for msg in websocket:
                await self.process_message(msg)

    async def process_message(self, msg):
        """Dispatches detected activity to the decoder."""
        # Ignore initial subscription confirmation results 
        if not hasattr(msg[0], 'params'):
            return 

        try:
            # Extract signature for Stage 3 decoding 
            signature = msg[0].params.result.value.signature
            print(f"Activity Detected! Signature: {signature}")
            
            # TODO: Integrate with decoder.py in Week 4 
        except Exception as e:
            print(f"Error processing activity: {e}")

if __name__ == "__main__":
    listener = WhaleListener()
    try:
        asyncio.run(listener.start())
    except KeyboardInterrupt:
        print("\nListener stopped.")