import os
import time
import psycopg2
from dotenv import load_dotenv
from typing import Dict, List, Optional
from datetime import datetime

load_dotenv()


"""
Class Name:
    Trade

Description:
    Represents a single executed trade within the paper trading system.
    Stores all relevant metadata about a buy or sell transaction.

Member Variables:
    token (str):
        The symbol or identifier of the traded asset.
    side (str):
        The trade direction ('BUY' or 'SELL').
    price (float):
        The executed price per token after slippage.
    amount (float):
        The quantity of tokens bought or sold.
    timestamp (datetime):
        The time at which the trade was executed.
"""
class Trade:

    """
    Method Name:
        __init__

    Parameters:
        token (str):
            Asset symbol being traded.
        side (str):
            'BUY' or 'SELL'.
        price (float):
            Executed price per token.
        amount (float):
            Quantity of tokens traded.
        timestamp (datetime):
            Execution time of the trade.

    Return:
        None

    Method Description:
        Initializes a Trade object with all relevant
        transaction details for tracking and history storage.
    """
    def __init__(self, token: str, side: str, price: float, amount: float, timestamp: datetime):
        self.token = token
        self.side = side
        self.price = price
        self.amount = amount
        self.timestamp = timestamp


"""
Class Name:
    PaperAccount

Description:
    Simulates a paper trading account for copy trading strategies.
    Tracks balance, open positions, and trade history while applying
    simplified slippage assumptions. Pulls real swap data from a
    PostgreSQL database configured via DATABASE_URL in .env.

Member Variables:
    balance (float):
        Current available USD balance.
    positions (Dict[str, float]):
        Mapping of token symbol to amount currently held.
    tradeHistory (List[Trade]):
        List of all executed trades.
    initialBalance (float):
        Starting account balance used for PnL calculation.
    _db_conn:
        Active psycopg2 database connection, or None if not connected.
"""
class PaperAccount:

    """
    Method Name:
        __init__

    Parameters:
        initialBalance (float):
            Starting account balance. Defaults to 10000.0 USD.

    Return:
        None

    Method Description:
        Initializes the paper trading account with a starting
        balance, empty positions dictionary, empty trade history,
        and opens a connection to the PostgreSQL database using
        DATABASE_URL from the environment.
    """
    def __init__(self, initialBalance: float = 10000.0):
        self.balance = initialBalance
        self.initialBalance = initialBalance
        self.positions: Dict[str, float] = {}
        self.tradeHistory: List[Trade] = []
        self._db_conn = self._connect_db()


    """
    Method Name:
        _connect_db

    Parameters:
        None

    Return:
        psycopg2 connection object, or None on failure.

    Method Description:
        Reads DATABASE_URL from the environment (populated by
        python-dotenv via the .env file) and opens a psycopg2
        connection. Returns None and prints a warning if the
        variable is missing or the connection fails.
    """
    def _connect_db(self):
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("WARNING: DATABASE_URL not found in environment / .env file.")
            return None
        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            print("Database connection established.")
            return conn
        except Exception as e:
            print(f"WARNING: Could not connect to database: {e}")
            return None


    """
    Method Name:
        _fetch_latest_swap

    Parameters:
        token_mint (str):
            The token_out_mint address to filter swaps by.
            Pass None to fetch the single most-recent swap
            across all tokens.

    Return:
        Optional[dict]:
            A dict with keys id, amount_in, price_per_token,
            timestamp, amount_out, owner, token_out_mint,
            token_in_mint — or None if no row exists or the
            database is unavailable.

    Method Description:
        Queries the swaps table for the latest record matching
        the given token_out_mint (or any token if None), ordered
        by timestamp descending, and returns the row as a plain dict.

        Columns read: id, amount_in, price_per_token, timestamp,
                      amount_out, owner, token_out_mint, token_in_mint
    """
    def _fetch_latest_swap(self, token_mint: Optional[str] = None) -> Optional[dict]:
        if self._db_conn is None:
            print("No database connection — skipping DB fetch.")
            return None

        try:
            cursor = self._db_conn.cursor()

            if token_mint:
                query = """
                    SELECT id, amount_in, price_per_token, timestamp,
                           amount_out, owner, token_out_mint, token_in_mint
                    FROM swaps
                    WHERE token_out_mint = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """
                cursor.execute(query, (token_mint,))
            else:
                query = """
                    SELECT id, amount_in, price_per_token, timestamp,
                           amount_out, owner, token_out_mint, token_in_mint
                    FROM swaps
                    ORDER BY timestamp DESC
                    LIMIT 1
                """
                cursor.execute(query)

            row = cursor.fetchone()
            cursor.close()

            if row is None:
                return None

            return {
                "id":              row[0],
                "amount_in":       float(row[1]),
                "price_per_token": float(row[2]),
                "timestamp":       row[3],
                "amount_out":      float(row[4]),
                "owner":           row[5],
                "token_out_mint":  row[6],
                "token_in_mint":   row[7],
            }

        except Exception as e:
            print(f"Database query error: {e}")
            return None


    """
    Method Name:
        executeCopy

    Parameters:
        token (str):
            Human-readable asset symbol (e.g. 'SOL', 'BONK').
            Used for position tracking and display only.
        price (float):
            Fallback market price used when no DB record is found.
        amountUSD (float):
            Fallback USD amount used when no DB record is found.
        token_mint (str, optional):
            The token_out_mint address to look up in the swaps table.
            When provided the method fetches real price_per_token and
            amount_in from PostgreSQL instead of using the arguments above.

    Return:
        bool:
            True if trade executed successfully.
            False if insufficient funds.

    Method Description:
        Simulates a copy-trade execution backed by live swap data.

        1. If token_mint is supplied (and a DB connection exists):
               - Fetches the latest swap row for that mint from the
                 swaps table.
               - Uses price_per_token and amount_in from the row.
               - Logs the originating owner wallet and swap ID.
        2. Falls back to the supplied price / amountUSD arguments when
           no DB record is available.
        3. Verifies sufficient account balance.
        4. Applies 2% slippage on the effective buy price.
        5. Updates balance, positions, and trade history.
    """
    def executeCopy(
        self,
        token: str,
        price: float,
        amountUSD: float,
        token_mint: Optional[str] = None,
    ) -> bool:

        effective_price = price
        effective_amount_usd = amountUSD

        # Pull swap data from the database when a mint address is supplied
        if token_mint:
            swap = self._fetch_latest_swap(token_mint)

            if swap:
                effective_price = swap["price_per_token"]
                effective_amount_usd = swap["amount_in"]

                print(
                    f"  [DB] Swap ID={swap['id']} | "
                    f"Owner={swap['owner']} | "
                    f"Token out={swap['token_out_mint']} | "
                    f"Token in={swap['token_in_mint']} | "
                    f"Amount in=${swap['amount_in']:.4f} | "
                    f"Price per token=${swap['price_per_token']:.6f} | "
                    f"Amount out={swap['amount_out']:.4f} | "
                    f"Timestamp={swap['timestamp']}"
                )
            else:
                print(f"  [DB] No swap found for mint {token_mint} — using fallback values.")

        if effective_amount_usd > self.balance:
            print(f"Insufficient funds to copy trade {token}")
            return False

        # Apply 2% slippage for buy orders
        slipped_price = effective_price * 1.02

        tokens_bought = effective_amount_usd / slipped_price
        self.balance -= effective_amount_usd
        self.positions[token] = self.positions.get(token, 0) + tokens_bought

        self.tradeHistory.append(
            Trade(token, 'BUY', slipped_price, tokens_bought, datetime.now())
        )

        return True


    """
    Method Name:
        sellPosition

    Parameters:
        token (str):
            Asset symbol being sold.
        price (float):
            Current market price.
        amount (float):
            Quantity of tokens to sell.

    Return:
        bool:
            True if sale executed successfully.
            False if insufficient position size.

    Method Description:
        Simulates selling a held position.

        - Verifies sufficient token holdings.
        - Applies assumed slippage (2% worse price for sells).
        - Updates account balance and reduces position.
        - Removes token entry if position reaches zero.
        - Records trade in trade history.
    """
    def sellPosition(self, token: str, price: float, amount: float) -> bool:
        if token not in self.positions or self.positions[token] < amount:
            return False

        # Apply 2% slippage for sell orders
        effective_price = price * 0.98

        gain_usd = amount * effective_price
        self.balance += gain_usd
        self.positions[token] -= amount

        if self.positions[token] <= 0:
            del self.positions[token]

        self.tradeHistory.append(
            Trade(token, 'SELL', effective_price, amount, datetime.now())
        )

        return True


    """
    Method Name:
        getPortfolioValue

    Parameters:
        currentPrices (Dict[str, float]):
            Mapping of token symbol to current market price.

    Return:
        float:
            Total portfolio value (cash + open positions).

    Method Description:
        Calculates total portfolio value by summing:
            - Current cash balance
            - Market value of all open positions
    """
    def getPortfolioValue(self, currentPrices: Dict[str, float]) -> float:
        total_value = self.balance

        for token, amount in self.positions.items():
            price = currentPrices.get(token, 0)
            total_value += amount * price

        return total_value


    """
    Method Name:
        getPnL

    Parameters:
        currentPrices (Dict[str, float]):
            Mapping of token symbol to current market price.

    Return:
        float:
            Profit or loss relative to initial balance.

    Method Description:
        Computes unrealized + realized PnL by subtracting
        the initial account balance from current portfolio value.
    """
    def getPnL(self, currentPrices: Dict[str, float]) -> float:
        return self.getPortfolioValue(currentPrices) - self.initialBalance


    """
    Method Name:
        getBalance

    Parameters:
        None

    Return:
        float:
            Current available cash balance.

    Method Description:
        Returns the account's available USD balance.
    """
    def getBalance(self) -> float:
        return self.balance


    """
    Method Name:
        getPositions

    Parameters:
        None

    Return:
        Dict[str, float]:
            Dictionary mapping token symbols to amounts held.

    Method Description:
        Returns the current open positions in the account.
    """
    def getPositions(self) -> Dict[str, float]:
        return self.positions


    """
    Method Name:
        close

    Parameters:
        None

    Return:
        None

    Method Description:
        Cleanly closes the PostgreSQL database connection.
        Call this before the process exits.
    """
    def close(self):
        if self._db_conn:
            self._db_conn.close()
            print("Database connection closed.")


# ---------------------------------------------------------------------------
# Mock data — used as fallback when the DB has no entry for a given token
# ---------------------------------------------------------------------------
mock_prices = {
    "SOL":        150.00,
    "BONK":       0.02,
    "JUP":        1.10,
    "Dogwithhat": 2.30,
    "Render":     6.15,
    "Popcat":     0.98,
}

# Map human-readable ticker -> on-chain mint address
# Replace placeholder values with real Solana mint addresses
mock_mints = {
    "SOL":        "So11111111111111111111111111111111111111112",
    "BONK":       "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JUP":        "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "Dogwithhat": "DoGWithHatMintAddressPlaceholder1111111111111",
    "Render":     "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",
    "Popcat":     "PopcatMintAddressPlaceholder111111111111111111",
}


if __name__ == "__main__":
    import random

    my_account = PaperAccount(initialBalance=10000.0)
    print(f"Account Initialized. Balance: ${my_account.getBalance():.2f}\n")

    test_buy_amount = 100.0  # Fallback USD amount if DB has no data

    try:
        while True:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] --- Trade Triggered ---")

            token, fallback_price = random.choice(list(mock_prices.items()))
            token_mint = mock_mints.get(token)

            success = my_account.executeCopy(
                token=token,
                price=fallback_price,
                amountUSD=test_buy_amount,
                token_mint=token_mint,
            )

            if success:
                print(
                    f"Bought {token} (mint={token_mint}) | "
                    f"New Balance: ${my_account.getBalance():.2f}"
                )
            else:
                print("Trade failed — insufficient funds.")

            portfolio_val = my_account.getPortfolioValue(mock_prices)
            pnl = my_account.getPnL(mock_prices)
            print(
                f"Portfolio: ${portfolio_val:.2f} | "
                f"Cash: ${my_account.getBalance():.2f} | "
                f"PnL: ${pnl:.2f}\n"
            )

            time.sleep(10)

    except KeyboardInterrupt:
        print("\nPaper Trader shutting down...")
        my_account.close()