import asyncio
import os
import json
from pathlib import Path
from dotenv import load_dotenv  
from solana.rpc.websocket_api import connect
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.pubkey import Pubkey
from solders.rpc.responses import SubscriptionResult, LogsNotification
from trader.engine.decoder import Decoder

load_dotenv()
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")

class WhaleListener:
    def __init__(self, rpc_url=f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"):
        self.rpc_url = rpc_url
        self.targets = self._load_targets()
        self.last_seen = {}   # wallet -> last processed signature

    def _load_targets(self):
        base_path = Path(__file__).parent.parent
        file_path = base_path / "data" / "whales.json"
        if not file_path.exists():
            print(f"ERROR: Whale file not found at {file_path}")
            return []
        try:
            import json
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
            subscribed_addresses = []
            for address in self.targets:
                try:
                    pubkey = Pubkey.from_string(address)
                    await websocket.logs_subscribe(
                        filter_=RpcTransactionLogsFilterMentions(pubkey),
                        commitment="confirmed",
                    )
                    subscribed_addresses.append(address)
                except Exception as e:
                    print(f"Failed to subscribe to {address}: {e}")

            if not subscribed_addresses:
                print("No subscriptions sent. Aborting.")
                return

            subscription_map = {}
            confirmed = 0
            needed = len(subscribed_addresses)

            async for msg in websocket:
                try:
                    notif = msg[0]
                except (IndexError, TypeError):
                    continue

                if isinstance(notif, SubscriptionResult):
                    sub_id = notif.result
                    if confirmed < needed:
                        address = subscribed_addresses[confirmed]
                        subscription_map[sub_id] = address
                        confirmed += 1
                        print(f"Subscribed to {address[:6]}...{address[-4:]} (id: {sub_id})")
                        if confirmed >= needed:
                            print(f"All {confirmed} subscriptions confirmed. Monitoring whales...")

                elif isinstance(notif, LogsNotification):
                    # Fire and forget — never await decode work inside the websocket loop
                    asyncio.create_task(
                        self._process_message(notif, subscription_map)
                    )

    async def _decode_with_retry(self, signature: str, max_attempts: int = 5, base_delay: float = 1.5):
        """Retry decode_swap with exponential backoff to allow the tx to propagate."""
        for attempt in range(max_attempts):
            try:
                result = await asyncio.to_thread(self.decoder.decode_swap, signature)
                return result
            except Exception as e:
                err_str = str(e).lower()
                if "not found" in err_str or err_str == "":
                    delay = base_delay * (2 ** attempt)
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(delay)
                    else:
                        print(f"Gave up decoding {signature[:12]}... after {max_attempts} attempts")
                else:
                    print(f"Decode error for {signature[:12]}...: {type(e).__name__}: {e}")
                    return

    async def _process_message(self, notif: "LogsNotification", subscription_map: dict):
        try:
            sub_id = notif.subscription
            whale_address = subscription_map.get(sub_id, "unknown")

            value = notif.result.value
            signature = str(value.signature)
            err = value.err

            if not signature:
                return

            if err is not None:
                print(f"Transaction {signature} for {whale_address[:6]}...{whale_address[-4:]} failed (err: {err})")
                return

            print(f"\nWhale activity detected! Wallet: {whale_address[:6]}...{whale_address[-4:]} | Sig: {signature}")
            await self._decode_with_retry(signature)

        except Exception as e:
            print(f"Error processing message: {type(e).__name__}: {e}")

    async def start(self):
        if not self.targets:
            print("No whale addresses to monitor. Exiting.")
            return

        retry_delay = 10
        while True:
            try:
                pubkey = Pubkey.from_string(wallet)
                resp = self.client.get_signatures_for_address(pubkey, limit=1)
                if resp.value:
                    self.last_seen[wallet] = str(resp.value[0].signature)
                else:
                    self.last_seen[wallet] = None
                    
            except Exception as e:
                print(f"Init error for {wallet}: {e}")
                self.last_seen[wallet] = None

        print("Polling started. Will check every", self.poll_interval, "seconds.")

        while True:
            start_time = time.time()
            # Check all wallets sequentially (or you could use asyncio.gather for speed)
            for wallet in self.targets:
                await self._check_wallet(wallet)
            elapsed = time.time() - start_time
            sleep_time = max(0, self.poll_interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    listener = PollingWhaleListener(poll_interval=5)  # check every 5 seconds
    try:
        asyncio.run(listener.start())
    except KeyboardInterrupt:
        print("\nPolling listener stopped.")


# import asyncio
# import json
# from pathlib import Path
# from solana.rpc.websocket_api import connect
# from solders.rpc.config import RpcTransactionLogsFilterMentions
# from solders.pubkey import Pubkey
# from trader.engine.decoder import Decoder   # adjust import if needed

# class WhaleListener:
#     def __init__(self, rpc_url="wss://api.mainnet-beta.solana.com"):
#         self.rpc_url = rpc_url
#         self.targets = self._load_targets()
#         self.decoder = Decoder()

#     def _load_targets(self):
#         # listener.py is in engine/, so go up one level to reach data/
#         base_path = Path(__file__).parent.parent
#         file_path = base_path / "data" / "whales.json"

#         if not file_path.exists():
#             print(f"ERROR: Whale file not found at {file_path}")
#             return []

#         try:
#             with open(file_path, "r") as f:
#                 data = json.load(f)

#             if isinstance(data, dict) and "wallets" in data:
#                 wallets = data["wallets"]
#             elif isinstance(data, list):
#                 wallets = data
#             else:
#                 print(f"ERROR: Unexpected JSON format in {file_path}")
#                 return []

#             addresses = [w for w in wallets if isinstance(w, str)]
#             print(f"Loaded {len(addresses)} whale addresses from {file_path}")
#             return addresses

#         except Exception as e:
#             print(f"Error reading {file_path}: {e}")
#             return []

#     async def _connect_and_listen(self):
#         async with connect(self.rpc_url) as websocket:
#             subscription_map = {}
#             for address in self.targets:
#                 try:
#                     await websocket.logs_subscribe(
#                         filter_=RpcTransactionLogsFilterMentions(Pubkey.from_string(address))
#                     )
#                     resp = await websocket.recv()
#                     sub_id = resp[0].result
#                     subscription_map[sub_id] = address
#                     print(f"Subscribed to {address[:6]}...{address[-4:]} (id: {sub_id})")
#                 except Exception as e:
#                     print(f"Failed to subscribe to {address}: {e}")

#             print(f"Monitoring {len(subscription_map)} whales...")
#             async for msg in websocket:
#                 await self._process_message(msg)

#     async def _process_message(self, msg):
#         try:
#             notif = msg[0]  # LogsNotification object
            
#             # Check if this is a logs notification (it should be, but be safe)
#             if not hasattr(notif, 'params'):
#                 return
            
#             # Extract data using attribute access (not dict .get())
#             params = notif.params
#             result = params.result
#             value = result.value
#             signature = str(value.signature)   # convert to string if needed
#             err = value.err
            
#             if not signature:
#                 return
#             if err is not None:
#                 print(f"Transaction {signature} failed (err: {err})")
#                 return
            
#             print(f"\n🚨 Whale activity detected! Signature: {signature}")
#             await asyncio.to_thread(self.decoder.decode_swap, signature)
            
#         except Exception as e:
#             print(f"Error processing message: {e}")

    

#     async def start(self):
#         if not self.targets:
#             print("No whale addresses to monitor. Exiting.")
#             return
#         retry_delay = 10
#         while True:
#             try:
#                 await self._connect_and_listen()
#             except Exception as e:
#                 print(f"WebSocket connection lost: {e}")
#                 print(f"Reconnecting in {retry_delay} seconds...")
#                 await asyncio.sleep(retry_delay)

# if __name__ == "__main__":
#     listener = WhaleListener()
#     try:
#         asyncio.run(listener.start())
#     except KeyboardInterrupt:
#         print("\nListener stopped by user.")