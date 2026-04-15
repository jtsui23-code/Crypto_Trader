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
        self.decoder = Decoder()

    def _load_targets(self):
        base_path = Path(__file__).parent.parent
        file_path = base_path / "data" / "whales.json"

        if not file_path.exists():
            return []

        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            if isinstance(data, dict) and "wallets" in data:
                wallets = data["wallets"]
            elif isinstance(data, list):
                wallets = data
            else:
                print(f"ERROR: Expected list in whales.json, got {type(data)}")
                return []

            addresses = [w for w in wallets if isinstance(w, str)]
            return addresses

        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return []

    async def _watch_config_changes(self, main_task):
        """Background task that monitors whales.json and forces a reconnect if it changes."""
        base_path = Path(__file__).parent.parent
        file_path = base_path / "data" / "whales.json"
        last_mtime = os.path.getmtime(file_path) if file_path.exists() else 0

        try:
            while True:
                await asyncio.sleep(2)
                current_mtime = os.path.getmtime(file_path) if file_path.exists() else 0
                if current_mtime > last_mtime:
                    last_mtime = current_mtime
                    new_targets = self._load_targets()
                    # If the targets actually changed, trigger a reset
                    if set(new_targets) != set(self.targets):
                        print("\n[!] Whales config updated! Forcing listener restart...")
                        self.targets = new_targets
                        main_task.cancel()
                        break
        except asyncio.CancelledError:
            pass

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

            # Start the background watcher
            main_task = asyncio.current_task()
            watcher_task = asyncio.create_task(self._watch_config_changes(main_task))

            try:
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
                        # Fire and forget
                        asyncio.create_task(self._process_message(notif, subscription_map))
            finally:
                watcher_task.cancel() # Clean up the watcher if websocket drops

    async def _decode_with_retry(self, signature: str, max_attempts: int = 5, base_delay: float = 1.5):
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

            if not signature or err is not None:
                return

            print(f"\nWhale activity detected! Wallet: {whale_address[:6]}...{whale_address[-4:]} | Sig: {signature}")
            await self._decode_with_retry(signature)

        except Exception as e:
            print(f"Error processing message: {type(e).__name__}: {e}")

    async def start(self):
        retry_delay = 5
        # The main loop will keep the listener running indefinitely, attempting to reconnect if the connection drops or if the config changes. It also handles the case where there are no targets to monitor, waiting for the user to add some instead of exiting.
        while True:
            # If empty, wait for the user to add whales instead of exiting completely
            if not self.targets:
                print("No whale addresses to monitor. Waiting for targets...")
                await asyncio.sleep(retry_delay)
                self.targets = self._load_targets()
                continue

            self.decoder.whales = set(self.targets)
            listener_task = asyncio.create_task(self._connect_and_listen())

            try:
                # This will run until the websocket connection drops or the watcher triggers a cancel
                await listener_task
            except asyncio.CancelledError:
                # Triggers immediate reconnect without the 5 second delay
                continue
            # Catch-all to prevent the listener from crashing due to unexpected errors. It will log the error and attempt to reconnect after a delay.
            except Exception as e:
                print(f"Disconnected: {e}")

            print(f"Reconnecting in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)

if __name__ == "__main__":
    listener = WhaleListener()
    try:
        asyncio.run(listener.start())
    except KeyboardInterrupt:
        print("\nListener stopped by user.")