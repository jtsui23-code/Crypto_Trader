import asyncio
import json
from pathlib import Path
from solana.rpc.websocket_api import connect
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.pubkey import Pubkey
from trader.engine.decoder import Decoder   # adjust import if needed

class WhaleListener:
    def __init__(self, rpc_url="wss://api.mainnet-beta.solana.com"):
        self.rpc_url = rpc_url
        self.targets = self._load_targets()
        self.decoder = Decoder()

    def _load_targets(self):
        # listener.py is in engine/, so go up one level to reach data/
        base_path = Path(__file__).parent.parent
        file_path = base_path / "data" / "whales.json"

        if not file_path.exists():
            print(f"ERROR: Whale file not found at {file_path}")
            return []

        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            if isinstance(data, dict) and "wallets" in data:
                wallets = data["wallets"]
            elif isinstance(data, list):
                wallets = data
            else:
                print(f"ERROR: Unexpected JSON format in {file_path}")
                return []

            addresses = [w for w in wallets if isinstance(w, str)]
            print(f"Loaded {len(addresses)} whale addresses from {file_path}")
            return addresses

        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return []

    async def _connect_and_listen(self):
        async with connect(self.rpc_url) as websocket:
            subscription_map = {}
            for address in self.targets:
                try:
                    await websocket.logs_subscribe(
                        filter_=RpcTransactionLogsFilterMentions(Pubkey.from_string(address))
                    )
                    resp = await websocket.recv()
                    sub_id = resp[0].result
                    subscription_map[sub_id] = address
                    print(f"Subscribed to {address[:6]}...{address[-4:]} (id: {sub_id})")
                except Exception as e:
                    print(f"Failed to subscribe to {address}: {e}")

            print(f"Monitoring {len(subscription_map)} whales...")
            async for msg in websocket:
                await self._process_message(msg)

    async def _process_message(self, msg):
        try:
            notif = msg[0]
            if notif.get("method") != "logsNotification":
                return
            params = notif.get("params", {})
            result = params.get("result", {})
            value = result.get("value", {})
            signature = value.get("signature")
            err = value.get("err")
            if not signature:
                return
            if err is not None:
                print(f"Transaction {signature} failed (err: {err})")
                return
            print(f"\n🚨 Whale activity detected! Signature: {signature}")
            await asyncio.to_thread(self.decoder.decode_swap, signature)
        except Exception as e:
            print(f"Error processing message: {e}")

    async def start(self):
        if not self.targets:
            print("No whale addresses to monitor. Exiting.")
            return
        retry_delay = 10
        while True:
            try:
                await self._connect_and_listen()
            except Exception as e:
                print(f"WebSocket connection lost: {e}")
                print(f"Reconnecting in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)

if __name__ == "__main__":
    listener = WhaleListener()
    try:
        asyncio.run(listener.start())
    except KeyboardInterrupt:
        print("\nListener stopped by user.")