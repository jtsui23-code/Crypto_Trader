import asyncio
import json
from pathlib import Path
from solana.rpc.websocket_api import connect
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.pubkey import Pubkey
from trader.engine.decoder import Decoder


class WhaleListener:
    def __init__(self, rpc_url="wss://api.mainnet-beta.solana.com"):
        self.rpc_url = rpc_url
        self.targets = self._load_targets()
        self.decoder = Decoder()

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

    async def _listen_to_wallet(self, target):
        """Opens a dedicated WebSocket connection for a single wallet."""
        if isinstance(target, dict):
            address = target.get('address')
            tag = target.get('tag', 'Unknown')
        else:
            address = target
            tag = f"Whale_{address[:4]}"

        if not address:
            return

        async with connect(self.rpc_url) as websocket:
            await websocket.logs_subscribe(
                filter_=RpcTransactionLogsFilterMentions(
                    Pubkey.from_string(address)
                )
            )

            # Consume the subscription confirmation response
            resp = await websocket.recv()
            print(f"Subscribed to {tag}: {address} (sub id: {resp[0].result})")

            async for msg in websocket:
                await self.process_message(msg)

    async def start(self):
        if not self.targets:
            print("No target whales found. Exiting.")
            return

        print(f"Monitoring {len(self.targets)} whales for real-time activity...")

        # Run one persistent listener per wallet concurrently
        await asyncio.gather(
            *[self._listen_to_wallet(target) for target in self.targets]
        )

    async def process_message(self, msg):
        if not msg or not hasattr(msg[0], 'params'):
            return

        try:
            signature = msg[0].params.result.value.signature
            print(f"Activity Detected! Signature: {signature}")
            await asyncio.to_thread(self.decoder.decode_swap, signature)

        except Exception as e:
            print(f"Error processing activity: {e}")


if __name__ == "__main__":
    listener = WhaleListener()

    try:
        asyncio.run(listener.start())
    except KeyboardInterrupt:
        print("\nListener stopped.")