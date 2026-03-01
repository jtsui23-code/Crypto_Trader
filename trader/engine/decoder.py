import os
import psycopg2
from solana.rpc.api import Client
from solders.signature import Signature
from dotenv import load_dotenv

from sympy import diff

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
RPC_URL = "https://api.mainnet-beta.solana.com"
client = Client(RPC_URL)

def save_to_db(owner, mint, change):
    """Saves buy data to Neon database after converting Pubkeys to strings."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS buys (
                id SERIAL PRIMARY KEY,
                owner TEXT,
                mint TEXT,
                amount FLOAT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Explicitly cast to string to fix 'can't adapt type' error
        cur.execute(
            "INSERT INTO buys (owner, mint, amount) VALUES (%s, %s, %s)",
            (str(owner), str(mint), change)
        )
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")

def fetch_transaction(signature: str):
    tx = client.get_transaction(
        Signature.from_string(signature),
        encoding="jsonParsed",
        max_supported_transaction_version=0
    )
    return tx.value

def decode_token_changes(tx: str):
    meta = tx.transaction.meta

    pre = meta.pre_token_balances
    post = meta.post_token_balances

    changes = []

    for p in post:
        owner = p.owner
        mint = p.mint
        post_amt = float(p.ui_token_amount.ui_amount or 0)

        pre_amt = 0
        for pre_token in pre:
            if pre_token.owner == owner and pre_token.mint == mint:
                pre_amt = float(pre_token.ui_token_amount.ui_amount or 0)

        diff = post_amt - pre_amt

        if diff != 0:
            changes.append({
                "owner": owner,
                "mint": mint,
                "change": diff
            })

    return changes

def decode_swap(signature: str):
    tx = fetch_transaction(signature)
    if not tx:
        print("Transaction not found")
        return

    changes = decode_token_changes(tx)

    for change in changes:
        owner_str = str(change['owner'])
        mint_str = str(change['mint'])
        diff = change['change']
        
        if owner_str in TARGET_WALLETS:
            if diff > 0:
                save_to_db(owner_str, mint_str, diff)



decode_swap("2VCmivFuqztjSQDPR3nVhF6Vyuk9NHqqFrCHqkFSifzKC4ewTUGoUZCSrXd8YAzXSGExdR4Weypr8EGk9kMGd6M2")