import asyncio
import time
from pathlib import Path
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from decoder import Decoder   # your decoder class

class PollingWhaleListener:
    def __init__(self, rpc_url="https://api.mainnet-beta.solana.com", poll_interval=5):
        self.client = Client(rpc_url)
        self.decoder = Decoder(rpc_url=rpc_url)   # pass same RPC for consistency
        self.poll_interval = poll_interval
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

    async def _check_wallet(self, wallet):
        """Check for new transactions on a single wallet."""
        try:
            pubkey = Pubkey.from_string(wallet)
            resp = self.client.get_signatures_for_address(pubkey, limit=1)
            if not resp.value:
                return
            
            # Polls the latest signautre to see if something new happened.
            latest_sig = str(resp.value[0].signature)

            # Gets thes the last saved signature
            last = self.last_seen.get(wallet)

            # Sees if the polled singature is new
            if latest_sig != last:
                print(f"\n📡 New activity on {wallet[:6]}...{wallet[-4:]}: {latest_sig}")
                # Process the new transaction (this will call decode_swap and save to DB)
                await asyncio.to_thread(self.decoder.decode_swap, latest_sig)
                self.last_seen[wallet] = latest_sig

        except Exception as e:
            print(f"Error checking wallet {wallet}: {e}")

    async def start(self):
        if not self.targets:
            print("No whale addresses to monitor. Exiting.")
            return

        # Initialize last_seen with the current latest signature for each wallet
        print("Initializing last seen signatures...")
        for wallet in self.targets:
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