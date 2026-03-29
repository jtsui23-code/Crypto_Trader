import os
import json
import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn


# Load environment variables from trader/.env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI()

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
    
@app.get("/api/traders")
async def get_targeted_wallets():
    # Use the absolute path as it exists inside the Docker container
    file_path = "/app/trader/data/whales.json" 
    try:
        if not os.path.exists(file_path):
            print(f"ERROR: File not found at {file_path}")
            raise HTTPException(status_code=404, detail="whales.json file missing on server")
            
        with open(file_path, "r") as f:
            data = json.load(f)
        
        return [
            {"id": str(i), "name": address, "record": "Tracked"} 
            for i, address in enumerate(data.get("wallets", []))
        ]
    except Exception as e:
        print(f"Error reading whales: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

if __name__ == "__main__":
    print("Starting API server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)