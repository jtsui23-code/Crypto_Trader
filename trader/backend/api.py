import os
import json
import requests
from fastapi.staticfiles import StaticFiles
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import WebSocket, WebSocketDisconnect, BackgroundTasks
from typing import Dict, List, Any
from pydantic import BaseModel
import asyncio
import psycopg2.extras

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

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI()    
manager = ConnectionManager()

WHALES_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "whales.json")
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "config.json")
ENGINE_URL = "http://paper_trader:8001"

lstm_dir = "/app/trader/lstm"
if not os.path.exists(lstm_dir):
    os.makedirs(lstm_dir, exist_ok=True)

app.mount("/plots", StaticFiles(directory=lstm_dir), name="plots")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

db_pool = None

def init_db_pool():
    global db_pool
    if db_pool is None:
        try:
            db_pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=os.getenv("DATABASE_URL")
            )
        except Exception as e:
            print(f"Failed to initialize database pool: {e}")

@contextmanager
def get_db_connection():
    """Context manager to safely get and return connections to the pool."""
    global db_pool
    if db_pool is None:
        init_db_pool()
        
    if not db_pool:
        # Avoid raising HTTPException in background tasks
        raise RuntimeError("Database connection pool could not be initialized.")
        
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)

@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    if channel not in manager.active_connections:
        await websocket.close()
        return
        
    await manager.connect(websocket, channel)
    
    if channel == "forecast":
        try:
            lstm_json_path = "/app/trader/lstm/solana_lstm_data.json"
            if os.path.exists(lstm_json_path):
                with open(lstm_json_path, "r") as f:
                    await websocket.send_json(json.load(f))
        except Exception as e:
            print(f"Error sending initial forecast data: {e}")

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
    
@app.post("/api/internal/broadcast/{channel}")
async def broadcast_update(channel: str, data: dict):
    if channel in manager.active_connections:
        await manager.broadcast(data, channel)
    return {"status": "broadcasted"}

@app.post("/api/internal/trigger/{channel}")
async def trigger_channel_update(channel: str):
    import asyncio
    if channel not in manager.active_connections:
        return {"error": "Invalid channel"}
    
    data = None
    if channel == "traders":
        # Offload sync DB call to threadpool
        data = await asyncio.to_thread(get_targeted_wallets) 
    elif channel == "summary":
        data = await asyncio.to_thread(get_analytics_summary)
    elif channel == "forecast":
        try:
            lstm_json_path = "/app/trader/lstm/solana_lstm_data.json"
            if os.path.exists(lstm_json_path):
                with open(lstm_json_path, "r") as f:
                    data = json.load(f)
        except Exception as e:
            print(f"Error loading forecast JSON: {e}")
        
    if data:
        await manager.broadcast(data, channel)
        
    return {"status": "broadcasted"}

@app.get("/api/traders")
def get_targeted_wallets():
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            query = """
                SELECT 
                    wallet_address, winning_trades, losing_trades, 
                    best_trade_pnl, worst_trade_pnl, avg_pnl_per_trade, total_realised_pnl
                FROM paper_trader_performance
                ORDER BY total_realised_pnl DESC
            """
            cur.execute(query)
            rows = cur.fetchall()
            cur.close()

            return [
                {
                    "id": r[0], "name": r[0],
                    "record": f"${(r[6] or 0):.2f} Total PnL",
                    "winning_trades": r[1] or 0, "losing_trades": r[2] or 0,
                    "best_trade_pnl": float(r[3] or 0), "worst_trade_pnl": float(r[4] or 0),
                    "avg_pnl_per_trade": float(r[5] or 0), "total_pnl": float(r[6] or 0)
                } for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings/config")
def get_config():
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            return json.load(f)
    return {
        "risk_per_trade": 0.05, "take_profit_pct": 0.2, "take_profit_split": 0.7,
        "trailing_stop_pct": 0.35, "stop_loss_pct": 0.15, "max_hold_seconds": 70
    }

@app.get("/api/live-feed")
def get_live_feed():
    try:
        with get_db_connection() as conn:
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

            return [
                {
                    "symbol": r[0], "side": r[1], "price": float(r[2]),
                    "amount": float(r[3]), "usd_value": float(r[4]),
                    "sell_reason": r[5], "realised_pnl": float(r[6]) if r[6] is not None else None,
                    "timestamp": r[7].isoformat() if r[7] else None, "wallet_address": r[8]
                } for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/forecast-image")
def get_forecast_url():
    return {"url": "http://localhost:8000/plots/solana_lstm_forecast.png"}

@app.get("/api/analytics/summary")
def get_analytics_summary():
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            cur.execute("SELECT balance, initial_balance FROM paper_account LIMIT 1")
            acc = cur.fetchone()
            account_data = {"balance": float(acc[0]), "initial": float(acc[1])} if acc else {"balance": 0, "initial": 0}
            
            cur.execute("SELECT sell_reason, COUNT(*) FROM paper_trades WHERE side = 'SELL' GROUP BY sell_reason")
            reasons = [{"label": r[0] or "Unknown", "value": r[1]} for r in cur.fetchall()]
            
            cur.execute("SELECT token_symbol, SUM(cost_basis) FROM paper_positions GROUP BY token_symbol")
            exposure = [{"label": e[0], "value": float(e[1])} for e in cur.fetchall()]
            
            cur.execute("SELECT timestamp, realised_pnl FROM paper_trades WHERE realised_pnl IS NOT NULL ORDER BY timestamp ASC")
            pnl_history = []
            cum_pnl = 0.0
            for t in cur.fetchall():
                cum_pnl += float(t[1])
                pnl_history.append({"time": t[0].isoformat() if t[0] else None, "pnl": cum_pnl})
                
            cur.close()
            
            return {
                "account": account_data, "exit_reasons": reasons,
                "exposure": exposure, "pnl_history": pnl_history
            }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/swaps/{wallet_address}")
def get_wallet_history(wallet_address: str):
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            query = "SELECT token_out_mint, amount_out, token_in_mint, amount_in, timestamp FROM swaps WHERE owner = %s ORDER BY timestamp DESC"
            cur.execute(query, (wallet_address,))
            rows = cur.fetchall()
            cur.close()
            
            return [
                {
                    "token_out": r[0], "amount_out": r[1],
                    "token_in": r[2], "amount_in": r[3],
                    "time": r[4].isoformat() if r[4] else None
                } for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/portfolio/positions")
def get_paper_positions():
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            query = "SELECT token_out_mint, token_symbol, amount, entry_price, peak_price, cost_basis, wallet_address FROM paper_positions ORDER BY last_updated DESC"
            cur.execute(query)
            rows = cur.fetchall()
            cur.close()

            return [
                {
                    "id": r[0], "symbol": r[1], "amount": float(r[2]),
                    "entry_price": float(r[3]), "peak_price": float(r[4]),
                    "cost_basis": float(r[5]), "wallet_address": r[6]
                } for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings/whales")
def get_whales():
    if os.path.exists(WHALES_FILE_PATH):
        with open(WHALES_FILE_PATH, 'r') as f:
            return json.load(f)
    return {"wallets": []}


def _sync_db_and_engine(wallets: list[str]):
    """Handles the heavy DB operations and network requests."""
    # 1. High-Speed Database Sync
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            if wallets:
                cur.execute("DELETE FROM paper_trader_performance WHERE NOT (wallet_address = ANY(%s::text[]))", (wallets,))
            else:
                cur.execute("DELETE FROM paper_trader_performance")

            # FAST BULK INSERT: execute_values is exponentially faster than executemany
            insert_query = "INSERT INTO paper_trader_performance (wallet_address) VALUES %s ON CONFLICT (wallet_address) DO NOTHING"
            psycopg2.extras.execute_values(cur, insert_query, [(w,) for w in wallets])

            conn.commit()
            cur.close()
    except Exception as e:
        print(f"Database sync failed: {e}")

    # 2. Network Request
    try:
        requests.post(f"{ENGINE_URL}/command/update_config", json={}, timeout=2)
    except Exception as e:
        print(f"Engine notification failed: {e}")

async def _process_whales_background(wallets: list[str]):
    """Background pipeline that won't block the frontend API response."""
    await asyncio.to_thread(_sync_db_and_engine, wallets)
    updated_traders = await asyncio.to_thread(get_targeted_wallets)
    await manager.broadcast({"wallets": updated_traders}, "traders")

@app.post("/api/settings/whales")
async def update_whales(data: WhalesData, background_tasks: BackgroundTasks):
    data.wallets = list(dict.fromkeys(data.wallets))
    
    # 1. Update the local file instantly (Very fast)
    os.makedirs(os.path.dirname(WHALES_FILE_PATH), exist_ok=True)
    temp_path = WHALES_FILE_PATH + ".tmp"
    try:
        with open(temp_path, 'w') as f:
            json.dump({"wallets": data.wallets}, f, indent=2)
        os.replace(temp_path, WHALES_FILE_PATH)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e
    
    # 2. Hand off the slow DB and Engine work to a true background task
    background_tasks.add_task(_process_whales_background, data.wallets)

    # 3. Return instantly to the frontend UI
    return {"status": "processing_in_background"}

@app.post("/api/settings/config")
def update_config(data: EngineConfig):
    os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump(data.model_dump(), f, indent=2)

    try:
        resp = requests.post(f"{ENGINE_URL}/command/update_config", json=data.model_dump(), timeout=2)
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Engine unreachable: {e}")

@app.post("/api/engine/reset")
async def trigger_engine_reset(data: ResetData):
    import threading
    def _do_reset():
        try:
            requests.post(f"{ENGINE_URL}/command/reset", json=data.model_dump(), timeout=30)
        except Exception as e:
            print(f"[RESET] Engine reset request failed: {e}")

    threading.Thread(target=_do_reset, daemon=True).start()
    return {"status": "reset triggered"}