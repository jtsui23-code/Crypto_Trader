"""
insert_test_swap.py

Inserts a single test row into the swaps table so you can verify
the paper trading engine picks it up and executes a copy trade.

Usage:
    python insert_test_swap.py

The script will:
  1. Load DATABASE_URL and JUPITER_API_KEY from your .env file.
  2. Read the first whale wallet from data/whales.json to use as the owner
     (the engine only processes swaps whose owner is in that list).
  3. Insert a swap row with realistic values for SOL -> a test token.
  4. Print the inserted row's ID so you can confirm the engine reacts.
  5. Optionally clean up the test row afterwards.
"""

import os
import json
import psycopg2
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Test swap values — edit these if you want to test a specific token pair
# ---------------------------------------------------------------------------

# The input mint (what the whale BOUGHT / received) — using BONK as a realistic example
TOKEN_IN_MINT  = "7JAUDAWr5wHe1GRroDokhtkZcyncm2TF6GvoHzefpump"

# The output mint (what the whale SPENT to make the purchase) — SOL mint address
TOKEN_OUT_MINT = "So11111111111111111111111111111111111111112"

# How much of the input token the whale spent (e.g. 10 SOL)
AMOUNT_IN = 10.0

# How many output tokens were received (e.g. 1,000,000 BONK)
AMOUNT_OUT = 1_000_000.0

# Price of the output token per unit in USD at time of swap
PRICE_PER_TOKEN = 0.00002


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_first_whale() -> str:
    """Return the first wallet address from data/whales.json."""
    base_path = Path(__file__).parent.parent
    file_path = base_path / "data" / "whales.json"

    if not file_path.exists():
        raise FileNotFoundError(
            f"Could not find {file_path}.\n"
            "Make sure you run this script from the project root, or adjust the path."
        )

    with open(file_path, "r") as f:
        data = json.load(f)

    if isinstance(data, dict) and "wallets" in data:
        data = data["wallets"]

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("whales.json is empty or not a list of wallet addresses.")

    wallet = data[0]
    print(f"Using whale wallet: {wallet}")
    return wallet


def connect() -> psycopg2.extensions.connection:
    """Open a psycopg2 connection from DATABASE_URL."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL not set in environment / .env file.")
    conn = psycopg2.connect(url)
    conn.autocommit = True
    return conn


def insert_test_swap(conn, owner: str) -> int:
    """Insert one test swap row and return its generated id."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO swaps
            (amount_in, price_per_token, timestamp,
             amount_out, owner, token_out_mint, token_in_mint)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            AMOUNT_IN,
            PRICE_PER_TOKEN,
            datetime.now(timezone.utc),
            AMOUNT_OUT,
            owner,
            TOKEN_OUT_MINT,
            TOKEN_IN_MINT,
        ),
    )
    row_id = cursor.fetchone()[0]
    cursor.close()
    return row_id


def delete_test_swap(conn, row_id: int):
    """Remove the test row by id."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM swaps WHERE id = %s", (row_id,))
    cursor.close()
    print(f"Test row id={row_id} deleted.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Paper Trading Engine — Test Swap Inserter")
    print("=" * 60)

    # 1. Load whale wallet
    try:
        owner = load_first_whale()
    except (FileNotFoundError, ValueError) as e:
        print(f"\nERROR: {e}")
        return

    # 2. Connect to DB
    try:
        conn = connect()
        print("Database connection established.")
    except Exception as e:
        print(f"\nERROR connecting to database: {e}")
        return

    # 3. Insert the test swap
    try:
        row_id = insert_test_swap(conn, owner)
        print(f"\nInserted test swap row:")
        print(f"  id              : {row_id}")
        print(f"  owner           : {owner}")
        print(f"  token_in_mint   : {TOKEN_IN_MINT}  (token BOUGHT)")
        print(f"  token_out_mint  : {TOKEN_OUT_MINT}  (token SPENT)")
        print(f"  amount_in       : {AMOUNT_IN}")
        print(f"  amount_out      : {AMOUNT_OUT:,.0f}")
        print(f"  price_per_token : ${PRICE_PER_TOKEN}")
        print(f"\nThe paper trading engine should detect and copy this swap")
        print(f"within {5} seconds (next poll cycle).")
    except Exception as e:
        print(f"\nERROR inserting swap: {e}")
        conn.close()
        return

    # 4. Ask whether to clean up
    print()
    answer = input("Delete the test row now? (y/N): ").strip().lower()
    if answer == "y":
        try:
            delete_test_swap(conn, row_id)
        except Exception as e:
            print(f"ERROR deleting row: {e}")
    else:
        print(f"Leaving row id={row_id} in the table.")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()