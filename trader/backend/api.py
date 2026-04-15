import os
import json
import time
from fastapi.staticfiles import StaticFiles
import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Any
from pydantic import BaseModel
import requests

class WhalesData(BaseModel):
    wallets: List[str]

class EngineConfig(BaseModel):
    risk_per_trade: float
    take_profit_pct: float
    take_profit_split: float
    trailing_stop_pct: float
    stop_loss_pct: float
    max_hold_seconds: int

class ResetData(BaseModel):
    new_balance: float

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            "live_feed": [],
            "summary": [],
            "positions": [],
            "traders": [],
            "forecast": []
        }

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        self.active_connections[channel].append(websocket)

    def disconnect(self, websocket: WebSocket, channel: str):
        self.active_connections[channel].remove(websocket)

    async def broadcast(self, message: Any, channel: str):
        for connection in self.active_connections[channel]:
            await connection.send_json(message)



# Load environment variables from trader/.env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# Initialize FastAPI and the connection manager for WebSocket handling
app = FastAPI()    
manager = ConnectionManager()

WHALES_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "whales.json")
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "config.json")


# Define the base directory and the path to the LSTM module
lstm_dir = "/app/trader/lstm"

if not os.path.exists(lstm_dir):
    os.makedirs(lstm_dir, exist_ok=True)

app.mount("/plots", StaticFiles(directory=lstm_dir), name="plots")

# Enable CORS so the React frontend (typically on port 5173) can communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    """Establishes a connection to the PostgreSQL database using the environment variable."""
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None
    
@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    if channel not in manager.active_connections:
        await websocket.close()
        return
        
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text() # Keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
    
@app.post("/api/internal/broadcast/{channel}")
async def broadcast_update(channel: str, data: dict):
    if channel in manager.active_connections:
        await manager.broadcast(data, channel)
    return {"status": "broadcasted"}

@app.post("/api/internal/trigger/{channel}")
async def trigger_channel_update(channel: str):
    """
    Called by the engine to tell the API to fetch fresh DB data 
    and broadcast it to the requested WebSocket channel.
    """
    if channel not in manager.active_connections:
        return {"error": "Invalid channel"}
    
    data = None
    if channel == "traders":
        data = await get_targeted_wallets() 
    elif channel == "summary":
        data = await get_analytics_summary()
    elif channel == "forecast":
        # Append timestamp to bypass browser image cache
        data = {"url": f"http://localhost:8000/plots/solana_lstm_forecast.png?t={int(time.time())}"}
        
    if data:
        await manager.broadcast(data, channel)
        
    return {"status": "broadcasted"}

@app.get("/api/traders")
async def get_targeted_wallets():
    """
    Fetches performance metrics for all tracked wallets from the 
    paper_trader_performance table to populate frontend charts.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cur = conn.cursor()
        # Query the specific performance metrics required by the frontend charts
        query = """
            SELECT 
                wallet_address, 
                winning_trades, 
                losing_trades, 
                best_trade_pnl, 
                worst_trade_pnl, 
                avg_pnl_per_trade,
                total_realised_pnl
            FROM paper_trader_performance
            ORDER BY total_realised_pnl DESC
        """
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "id": r[0],
                "name": r[0],
                "record": f"${(r[6] or 0):.2f} Total PnL",
                "winning_trades": r[1] or 0,
                "losing_trades": r[2] or 0,
                "best_trade_pnl": float(r[3] or 0),
                "worst_trade_pnl": float(r[4] or 0),
                "avg_pnl_per_trade": float(r[5] or 0),
                "total_pnl": float(r[6] or 0)
            } for r in rows
        ]
    except Exception as e:
        if conn: conn.close()
        print(f"Error fetching performance data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# This endpoint retrieves the most recent 100 trades from the paper_trades table to display in the live feed on the frontend dashboard.
@app.get("/api/live-feed")
async def get_live_feed():
    """
    Fetches the most recent trading activities from the paper_trades table.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cur = conn.cursor()
        query = """
            SELECT token_symbol, side, price, amount, usd_value,
                   sell_reason, realised_pnl, timestamp, wallet_address
            FROM paper_trades
            ORDER BY timestamp DESC
            LIMIT 100
        """
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "symbol": r[0],
                "side": r[1],
                "price": float(r[2]),
                "amount": float(r[3]),
                "usd_value": float(r[4]),
                "sell_reason": r[5],
                "realised_pnl": float(r[6]) if r[6] is not None else None,
                "timestamp": r[7].isoformat() if r[7] else None,
                "wallet_address": r[8]
            } for r in rows
        ]
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

# This endpoint provides the URL to the latest forecast image generated by the LSTM model
@app.get("/api/forecast-image")
async def get_forecast_url():
    # Return the relative URL to the frontend
    return {"url": "http://localhost:8000/plots/solana_lstm_forecast.png"}

@app.get("/api/analytics/summary")
async def get_analytics_summary():
    conn = get_db_connection()
    if not conn: return {"error": "DB connection failed"}
    try:
        cur = conn.cursor()
        
        # Get Account Balance
        cur.execute("SELECT balance, initial_balance FROM paper_account LIMIT 1")
        acc = cur.fetchone()
        account_data = {"balance": float(acc[0]), "initial": float(acc[1])} if acc else {"balance": 0, "initial": 0}
        
        # Get Exit Reasons
        cur.execute("SELECT sell_reason, COUNT(*) FROM paper_trades WHERE side = 'SELL' GROUP BY sell_reason")
        reasons = [{"label": r[0] or "Unknown", "value": r[1]} for r in cur.fetchall()]
        
        # Get Exposure
        cur.execute("SELECT token_symbol, SUM(cost_basis) FROM paper_positions GROUP BY token_symbol")
        exposure = [{"label": e[0], "value": float(e[1])} for e in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        return {
            "account": account_data,
            "exit_reasons": reasons,
            "exposure": exposure
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/swaps/{wallet_address}")
async def get_wallet_history(wallet_address: str):
    """
    Queries the database for all recorded swaps associated 
    with a specific targeted wallet address.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cur = conn.cursor()
        # Query swaps where the owner matches the requested wallet address
        query = """
            SELECT token_out_mint, amount_out, token_in_mint, amount_in, timestamp 
            FROM swaps 
            WHERE owner = %s 
            ORDER BY timestamp DESC
        """
        cur.execute(query, (wallet_address,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        return [
            {
                "token_out": r[0],
                "amount_out": r[1],
                "token_in": r[2],
                "amount_in": r[3],
                "time": r[4].isoformat() if r[4] else None
            } for r in rows
        ]
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/portfolio/positions")
async def get_paper_positions():
    """
    Fetches all open positions from the paper_positions table.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cur = conn.cursor()
        # Retrieve all columns as defined in the paper_trader.py schema
        query = """
            SELECT token_out_mint, token_symbol, amount, entry_price, 
                   peak_price, cost_basis, wallet_address
            FROM paper_positions
            ORDER BY last_updated DESC
        """
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "id": r[0],             # token_out_mint
                "symbol": r[1],         # token_symbol
                "amount": float(r[2]),
                "entry_price": float(r[3]),
                "peak_price": float(r[4]),
                "cost_basis": float(r[5]),
                "wallet_address": r[6]
            } for r in rows
        ]
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings/whales")
async def get_whales():
    if os.path.exists(WHALES_FILE_PATH):
        with open(WHALES_FILE_PATH, 'r') as f:
            return json.load(f)
    return {"wallets": []}

ENGINE_URL = "http://paper_trader:8001"

@app.post("/api/settings/whales")
async def update_whales(data: WhalesData):
    # Remove duplicates while preserving order
    data.wallets = list(dict.fromkeys(data.wallets))

    os.makedirs(os.path.dirname(WHALES_FILE_PATH), exist_ok=True)
    with open(WHALES_FILE_PATH, 'w') as f:
        json.dump(data.model_dump(), f, indent=2)
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            
            if data.wallets:
                delete_query = """
                    DELETE FROM paper_trader_performance 
                    WHERE NOT (wallet_address = ANY(%s::text[]))
                """
                cur.execute(delete_query, (data.wallets,))
            else:
                cur.execute("DELETE FROM paper_trader_performance")

            add_query = """
                INSERT INTO paper_trader_performance (wallet_address)
                VALUES (%s)
                ON CONFLICT (wallet_address) DO NOTHING
            """
            
            for wallet in data.wallets:
                cur.execute(add_query, (wallet,))

            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Database sync failed: {e}")
            if conn: conn.close()
        
    try:
        requests.post(f"{ENGINE_URL}/command/update_config", json={}, timeout=2)
    except Exception as e:
        print(f"Engine notification failed: {e}")

    updated_traders = await get_targeted_wallets()
    await manager.broadcast({"wallets": updated_traders}, "traders")       

    return {"status": "success"}

@app.post("/api/settings/config")
def update_config(data: EngineConfig):
    # Forward the new config directly to the engine
    try:
        resp = requests.post(f"{ENGINE_URL}/command/update_config", json=data.dict(), timeout=2)
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Engine unreachable: {e}")

@app.post("/api/engine/reset")
def trigger_engine_reset(data: ResetData):
    try:
        resp = requests.post(f"{ENGINE_URL}/command/reset", json=data.dict(), timeout=5)
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Engine unreachable: {e}")