from solana.rpc.websocket_api import connect
import asyncio
import json

# Define the wallets you sourced in Stage 1
TARGETS = {"Fh3k...9Kp": "SOL_Whale_1"} 

async def listen():
    # Connect to the Solana Mainnet Beta WebSocket
    async with connect("wss://api.mainnet-beta.solana.com") as websocket:
        # Subscribe to logs mentioning your target addresses
        await websocket.logs_subscribe(
            mentions=list(TARGETS.keys())
        )
        
        print("Listening for whale activity...")
        
        # Continuously process incoming messages in real-time
        async for msg in websocket:
            print(msg)  # This msg contains the transaction signature