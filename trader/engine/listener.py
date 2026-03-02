import asyncio
from pathlib import Path
from solana.rpc.websocket_api import connect
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.pubkey import Pubkey
import json

def get_whales():
    base_path = Path(__file__).parent.parent
    file_path = base_path / "data" / "whales.json"

    try:
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
        else:
            print(f"Warning: {file_path} not found.")
            return []
    except Exception as e:
        print(f"Error reading whales.json: {e}")
        return []
    

async def listen():
    whale_data = get_whales()
    target_addresses = whale_data.get("wallets", [])
    
    if not target_addresses:
        print("No wallets found.")
        return

    # Using Helius or QuickNode is recommended for mainnet stability
    async with connect("wss://api.mainnet-beta.solana.com") as websocket:
        
        for address in target_addresses:
            # FIX: Use RpcTransactionLogsFilterMentions object instead of a plain dict
            await websocket.logs_subscribe(
                filter_=RpcTransactionLogsFilterMentions(Pubkey.from_string(address))
            )
            print(f"Subscribed to whale: {address}")
        
        print(f"Monitoring {len(target_addresses)} whales for real-time activity...")
        
        async for msg in websocket:
            print(f"Activity Detected: {msg}")


if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        print("Listener stopped.")