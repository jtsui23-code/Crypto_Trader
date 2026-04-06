import os
from dotenv import load_dotenv  
import psycopg2
import psycopg2.pool
from solana.rpc.api import Client
from solders.signature import Signature
from solana.rpc.core import RPCException
from dotenv import load_dotenv
from trader.scripts.get_whales import get_whales

SOL_MINT = "So11111111111111111111111111111111111111112"

load_dotenv()
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")

class Decoder:
    def __init__(self, rpc_url=f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"):
        load_dotenv()
        self.database_url = os.getenv("DATABASE_URL")
        self.rpc_url = rpc_url
        self.client = Client(self.rpc_url)
        self.whales = set(get_whales())
        print(f"[Decoder] RPC: {self.rpc_url[:60]}...")

        self._pool = psycopg2.pool.ThreadedConnectionPool(1, 10, self.database_url)
        self._ensure_table()

    def _ensure_table(self):
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS swaps (
                    id SERIAL PRIMARY KEY,
                    owner TEXT,
                    token_out_mint TEXT,
                    amount_out FLOAT,
                    token_in_mint TEXT,
                    amount_in FLOAT,
                    price_per_token FLOAT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            cur.close()
        finally:
            self._pool.putconn(conn)

    def _save_to_db(self, owner, token_out_mint, amount_out, token_in_mint, amount_in, price_per_token):
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO swaps (owner, token_out_mint, amount_out, token_in_mint, amount_in, price_per_token)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (owner, token_out_mint, amount_out, token_in_mint, amount_in, price_per_token)
            )
            conn.commit()
            cur.close()
        except Exception as e:
            print(f"Database error: {e}")
            conn.rollback()
        finally:
            self._pool.putconn(conn)

    def _fetch_transaction(self, signature: str):
        try:
            tx = self.client.get_transaction(
                Signature.from_string(signature),
                encoding="jsonParsed",
                max_supported_transaction_version=0
            )
            return tx.value
        except RPCException as e:
            if "not found" in str(e).lower():
                return None
            raise

    def _decode_token_changes(self, tx):
        meta = tx.transaction.meta
        pre = meta.pre_token_balances
        post = meta.post_token_balances

        pre_map = {}
        for b in pre:
            key = (str(b.owner), str(b.mint))
            pre_map[key] = float(b.ui_token_amount.ui_amount or 0)

        post_map = {}
        for b in post:
            key = (str(b.owner), str(b.mint))
            post_map[key] = float(b.ui_token_amount.ui_amount or 0)

        all_keys = set(pre_map.keys()) | set(post_map.keys())
        changes = []
        for key in all_keys:
            pre_amt = pre_map.get(key, 0)
            post_amt = post_map.get(key, 0)
            diff = post_amt - pre_amt
            if diff != 0:
                changes.append({"owner": key[0], "mint": key[1], "change": diff})
        return changes

    def _decode_sol_changes(self, tx):
        meta = tx.transaction.meta
        account_keys = tx.transaction.transaction.message.account_keys
        changes = []
        for i, (pre, post) in enumerate(zip(meta.pre_balances, meta.post_balances)):
            diff = (post - pre) / 1e9
            if abs(diff) > 0.0001:
                owner = str(account_keys[i].pubkey)
                changes.append({
                    "owner": owner,
                    "mint": SOL_MINT,
                    "change": diff
                })
        return changes

    def decode_swap(self, signature: str):
        tx = self._fetch_transaction(signature)
        if tx is None:
            raise ValueError(f"not found: {signature}")

        token_changes = self._decode_token_changes(tx)
        sol_changes = self._decode_sol_changes(tx)

        all_changes = token_changes.copy()
        for sol in sol_changes:
            already = any(
                c["owner"] == sol["owner"] and c["mint"] == sol["mint"]
                for c in token_changes
            )
            if not already:
                all_changes.append(sol)

        owners_in_tx = {c["owner"] for c in all_changes}
        whale_owners = owners_in_tx & self.whales
        if not whale_owners:
            return

        for owner in whale_owners:
            owner_changes = [c for c in all_changes if c["owner"] == owner]

            # SOL spent (negative SOL change) — the whale is buying a token with SOL
            sol_out = next((c for c in owner_changes if c["mint"] == SOL_MINT and c["change"] < 0), None)

            # Token received (positive non-SOL change)
            token_in = next((c for c in owner_changes if c["mint"] != SOL_MINT and c["change"] > 0), None)

            # Only save SOL -> token trades, ignore token -> SOL or token -> token
            if sol_out is None or token_in is None:
                return

            amount_sol = abs(sol_out["change"])
            amount_token = abs(token_in["change"])
            price_per_token = amount_sol / amount_token if amount_token else 0

            self._save_to_db(
                owner,
                SOL_MINT,
                amount_sol,
                token_in["mint"],
                amount_token,
                price_per_token
            )
            print(
                f"Swap saved: {owner[:6]}...{owner[-4:]} "
                f"spent {amount_sol:.4f} SOL for {amount_token:.2f} {token_in['mint'][:6]}... "
                f"@ {price_per_token:.10f} SOL/token"
            )