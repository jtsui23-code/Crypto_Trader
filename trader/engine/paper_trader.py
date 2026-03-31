import os
import json
import time
import requests
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Optional
from datetime import datetime, timezone

load_dotenv()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# How often the engine polls the swaps table for new whale trades (seconds)
POLL_INTERVAL_SECONDS = 5

# Fraction of current balance to risk on each copied trade (e.g. 0.05 = 5%)
RISK_PER_TRADE = 0.05

# --- Trailing Stop ---
# How far the price can drop from the position's peak before selling (e.g. 0.20 = 20%)
TRAILING_STOP_PCT = 0.20

# --- Time-Based Exit ---
# Maximum time to hold a position before force-selling (seconds)
MAX_HOLD_SECONDS = 300  # 30 minutes

# ---------------------------------------------------------------------------
# Other sell thresholds available for future experimentation (not yet active)
# ---------------------------------------------------------------------------
# TAKE_PROFIT_PCT       = 0.50   # Sell 100% when up X% from entry
# PARTIAL_TAKE_PROFIT   = {      # Sell portions at multiple targets
#     0.50: 0.50,                #   sell 50% of position at +50%
#     2.00: 0.50,                #   sell remaining 50% at +200%
# }
# STOP_LOSS_PCT         = 0.15   # Hard stop — sell immediately if down X% from entry
# MAX_ALLOCATION_PCT    = 0.30   # Trim position if it grows beyond X% of portfolio
# VOLUME_DROP_EXIT      = True   # Sell if 5-min volume drops sharply (needs price API extension)
# WHALE_EXIT_MIRROR     = True   # Sell when the whale sells the same token (full copy)


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
    Simulates a paper trading account that mirrors whale swaps detected
    by an external blockchain listener and stored in a PostgreSQL database.

    Buy side:
        Polls the swaps table periodically for new whale trades and
        mirrors them using a configurable risk-per-trade position size.

    Sell side:
        Autonomously manages open positions using a trailing stop and
        a time-based exit, evaluated against real-time Jupiter prices.

    Persistence:
        Saves and loads account state, open positions, trade history,
        and per-wallet performance metrics to/from PostgreSQL so progress
        survives restarts.

Member Variables:
    balance (float):
        Current available USD balance.
    positions (Dict[str, dict]):
        Open positions keyed by token_out_mint. Each entry holds:
            token_out_mint  - mint address of the held token
            token_symbol    - human readable label
            amount          - quantity of tokens held
            entry_price     - average price paid per token (after slippage)
            peak_price      - highest price seen since entry
            entry_time      - datetime the position was opened
            cost_basis      - total USD spent on the position
            wallet_address  - whale wallet that triggered the buy
    tradeHistory (List[Trade]):
        In-memory list of all trades executed this session.
    initialBalance (float):
        Starting account balance used for total PnL calculation.
    targets (list):
        Whale wallet addresses loaded from data/whales.json.
    _db_conn:
        Active psycopg2 database connection, or None if unavailable.
    _last_seen_swap_id (int):
        Highest swap ID already processed to avoid reprocessing.
"""
class PaperAccount:

    """
    Method Name:
        __init__

    Parameters:
        initialBalance (float):
            Starting account balance. Defaults to 10000.0 USD.
            Only used if no saved state exists in the database.

    Return:
        None

    Method Description:
        Loads the Jupiter API key from the environment, connects to the
        database, loads whale targets, restores any previously saved
        account state and open positions, and sets the baseline swap ID
        so only new swaps are processed.
    """
    def __init__(self, initialBalance: float = 10000.0):
        self.initialBalance = initialBalance
        self.balance = initialBalance
        self.positions: Dict[str, dict] = {}
        self.tradeHistory: List[Trade] = []
        self.targets: list = []

        self._price_cache: Dict[str, Optional[float]] = {}
        self._jupiter_api_key = os.getenv("JUPITER_API_KEY", "")
        if not self._jupiter_api_key:
            print("WARNING: JUPITER_API_KEY not found in environment / .env file.")

        self._db_conn = self._connect_db()
        self.targets = self._load_targets()
        self._ensure_trader_performance_rows()
        self._load_state()
        self._last_seen_swap_id = self._get_max_swap_id()


    # -----------------------------------------------------------------------
    # Whale target loading
    # -----------------------------------------------------------------------

    """
    Method Name:
        _load_targets

    Parameters:
        None

    Return:
        list:
            A list of whale wallet address strings.
            Returns an empty list if the file does not exist or is invalid.

    Method Description:
        Loads whale wallet addresses from data/whales.json.
        Handles both a direct list and a dict with a "wallets" key.
        Gracefully handles missing files and malformed JSON.
    """
    def _load_targets(self) -> list:
        base_path = Path(__file__).parent.parent
        file_path = base_path / "data" / "whales.json"

        try:
            if file_path.exists():
                with open(file_path, 'r') as f:
                    data = json.load(f)

                    if isinstance(data, dict) and "wallets" in data:
                        data = data["wallets"]

                    if not isinstance(data, list):
                        print(f"Error: Expected list in {file_path.name}, got {type(data)}")
                        return []

                    print(f"Loaded {len(data)} whale targets.")
                    return data
            else:
                print(f"Warning: {file_path} not found.")
                return []

        except Exception as e:
            print(f"Error reading whales.json: {e}")
            return []


    # -----------------------------------------------------------------------
    # Database connection
    # -----------------------------------------------------------------------

    """
    Method Name:
        _connect_db

    Parameters:
        None

    Return:
        psycopg2 connection object, or None on failure.

    Method Description:
        Reads DATABASE_URL from the environment and opens a persistent
        psycopg2 connection. Returns None and warns if unavailable.
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


    # -----------------------------------------------------------------------
    # State persistence — save and load
    # -----------------------------------------------------------------------

    """
    Method Name:
        _load_state

    Parameters:
        None

    Return:
        None

    Method Description:
        Restores account balance and open positions from the database
        on startup. If no saved state exists the engine starts fresh
        with initialBalance. Allows the engine to resume seamlessly
        after a restart without losing progress.
    """
    def _load_state(self):
        if self._db_conn is None:
            return

        try:
            cursor = self._db_conn.cursor()

            # Restore account balance
            cursor.execute("SELECT balance, initial_balance FROM paper_account LIMIT 1")
            row = cursor.fetchone()
            if row:
                self.balance = float(row[0])
                self.initialBalance = float(row[1])
                print(f"Restored account — Balance: ${self.balance:.2f}")
            else:
                print("No saved account state found, starting fresh.")

            # Restore open positions
            cursor.execute(
                """
                SELECT token_out_mint, token_symbol, amount, entry_price,
                       peak_price, entry_time, cost_basis, wallet_address
                FROM paper_positions
                """
            )
            rows = cursor.fetchall()
            for row in rows:
                entry_time = row[5]
                if entry_time.tzinfo is None:
                    entry_time = entry_time.replace(tzinfo=timezone.utc)

                self.positions[row[0]] = {
                    "token_out_mint": row[0],
                    "token_symbol":   row[1],
                    "amount":         float(row[2]),
                    "entry_price":    float(row[3]),
                    "peak_price":     float(row[4]),
                    "entry_time":     entry_time,
                    "cost_basis":     float(row[6]),
                    "wallet_address": row[7],
                }

            if rows:
                print(f"Restored {len(rows)} open position(s).")

            cursor.close()

        except Exception as e:
            print(f"Error loading state: {e}")


    """
    Method Name:
        _save_account

    Parameters:
        None

    Return:
        None

    Method Description:
        Upserts the current balance and initial_balance into the
        paper_account table. Always maintains a single row.
    """
    def _save_account(self):
        if self._db_conn is None:
            return
        try:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                UPDATE paper_account
                SET balance = %s, initial_balance = %s, last_updated = NOW()
                """,
                (self.balance, self.initialBalance)
            )
            cursor.close()
        except Exception as e:
            print(f"Error saving account: {e}")


    """
    Method Name:
        _save_position

    Parameters:
        token_out_mint (str):
            Mint address of the position to save or update.

    Return:
        None

    Method Description:
        Upserts a single open position into paper_positions.
        Uses INSERT ... ON CONFLICT to handle both new positions
        and updates to existing ones (e.g. after averaging in).
    """
    def _save_position(self, token_out_mint: str):
        if self._db_conn is None or token_out_mint not in self.positions:
            return
        try:
            pos = self.positions[token_out_mint]
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                INSERT INTO paper_positions
                    (token_out_mint, token_symbol, amount, entry_price,
                     peak_price, entry_time, cost_basis, wallet_address, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (token_out_mint) DO UPDATE SET
                    token_symbol  = EXCLUDED.token_symbol,
                    amount        = EXCLUDED.amount,
                    entry_price   = EXCLUDED.entry_price,
                    peak_price    = EXCLUDED.peak_price,
                    entry_time    = EXCLUDED.entry_time,
                    cost_basis    = EXCLUDED.cost_basis,
                    wallet_address = EXCLUDED.wallet_address,
                    last_updated  = NOW()
                """,
                (
                    pos["token_out_mint"],
                    pos["token_symbol"],
                    pos["amount"],
                    pos["entry_price"],
                    pos["peak_price"],
                    pos["entry_time"],
                    pos["cost_basis"],
                    pos["wallet_address"],
                )
            )
            cursor.close()
        except Exception as e:
            print(f"Error saving position {token_out_mint}: {e}")


    """
    Method Name:
        _delete_position

    Parameters:
        token_out_mint (str):
            Mint address of the position to remove.

    Return:
        None

    Method Description:
        Deletes a closed position from paper_positions after a sell.
    """
    def _delete_position(self, token_out_mint: str):
        if self._db_conn is None:
            return
        try:
            cursor = self._db_conn.cursor()
            cursor.execute(
                "DELETE FROM paper_positions WHERE token_out_mint = %s",
                (token_out_mint,)
            )
            cursor.close()
        except Exception as e:
            print(f"Error deleting position {token_out_mint}: {e}")


    """
    Method Name:
        _log_trade

    Parameters:
        wallet_address (str):
            Whale wallet that triggered the trade (empty string for sells).
        token_out_mint (str):
            Mint address of the traded token.
        token_symbol (str):
            Human readable token label.
        side (str):
            'BUY' or 'SELL'.
        price (float):
            Executed price per token after slippage.
        amount (float):
            Quantity of tokens traded.
        usd_value (float):
            Total USD value of the trade.
        sell_reason (str, optional):
            Reason the sell was triggered. None for buys.
        realised_pnl (float, optional):
            Realised profit or loss. None for buys.

    Return:
        None

    Method Description:
        Inserts a single trade record into paper_trades for
        permanent historical logging.
    """
    def _log_trade(
        self,
        wallet_address: str,
        token_out_mint: str,
        token_symbol: str,
        side: str,
        price: float,
        amount: float,
        usd_value: float,
        sell_reason: Optional[str] = None,
        realised_pnl: Optional[float] = None,
    ):
        if self._db_conn is None:
            return
        try:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                INSERT INTO paper_trades
                    (wallet_address, token_out_mint, token_symbol, side,
                     price, amount, usd_value, sell_reason, realised_pnl, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (wallet_address, token_out_mint, token_symbol, side,
                 price, amount, usd_value, sell_reason, realised_pnl)
            )
            cursor.close()
        except Exception as e:
            print(f"Error logging trade: {e}")


    # -----------------------------------------------------------------------
    # Trader performance tracking
    # -----------------------------------------------------------------------

    """
    Method Name:
        _ensure_trader_performance_rows

    Parameters:
        None

    Return:
        None

    Method Description:
        Inserts a default performance row for each whale wallet loaded
        from whales.json if one does not already exist. Uses
        INSERT ... ON CONFLICT DO NOTHING so existing rows are safe.
    """
    def _ensure_trader_performance_rows(self):
        if self._db_conn is None or not self.targets:
            return
        try:
            cursor = self._db_conn.cursor()
            for wallet in self.targets:
                cursor.execute(
                    """
                    INSERT INTO paper_trader_performance (wallet_address)
                    VALUES (%s)
                    ON CONFLICT (wallet_address) DO NOTHING
                    """,
                    (wallet,)
                )
            cursor.close()
            print(f"Performance rows ensured for {len(self.targets)} wallet(s).")
        except Exception as e:
            print(f"Error ensuring performance rows: {e}")


    """
    Method Name:
        _update_trader_performance

    Parameters:
        wallet_address (str):
            The whale wallet whose stats should be updated.
        realised_pnl (float):
            The PnL from the trade that just closed.

    Return:
        None

    Method Description:
        Updates the paper_trader_performance row for a wallet after
        a position closes. Increments trade counts, accumulates PnL,
        recalculates the average, and updates best/worst trade records.
    """
    def _update_trader_performance(self, wallet_address: str, realised_pnl: float):
        if self._db_conn is None or not wallet_address:
            return
        try:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                UPDATE paper_trader_performance SET
                    total_trades_copied = total_trades_copied + 1,
                    winning_trades      = winning_trades + CASE WHEN %s > 0 THEN 1 ELSE 0 END,
                    losing_trades       = losing_trades  + CASE WHEN %s < 0 THEN 1 ELSE 0 END,
                    total_realised_pnl  = total_realised_pnl + %s,
                    avg_pnl_per_trade   = (total_realised_pnl + %s) / (total_trades_copied + 1),
                    best_trade_pnl      = GREATEST(best_trade_pnl, %s),
                    worst_trade_pnl     = LEAST(worst_trade_pnl, %s),
                    last_trade_time     = NOW(),
                    last_updated        = NOW()
                WHERE wallet_address = %s
                """,
                (realised_pnl, realised_pnl, realised_pnl, realised_pnl,
                 realised_pnl, realised_pnl, wallet_address)
            )
            cursor.close()
        except Exception as e:
            print(f"Error updating trader performance for {wallet_address}: {e}")


    # -----------------------------------------------------------------------
    # Database swap polling
    # -----------------------------------------------------------------------

    """
    Method Name:
        _get_max_swap_id

    Parameters:
        None

    Return:
        int:
            The highest swap ID currently in the table, or 0 if empty.

    Method Description:
        Called once at startup to establish a baseline so the engine
        ignores swaps inserted before it started running.
    """
    def _get_max_swap_id(self) -> int:
        if self._db_conn is None:
            return 0
        try:
            cursor = self._db_conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM swaps")
            max_id = cursor.fetchone()[0]
            cursor.close()
            print(f"Baseline swap ID set to {max_id} — watching for new swaps above this.")
            return max_id
        except Exception as e:
            print(f"Could not fetch max swap ID: {e}")
            return 0


    """
    Method Name:
        _fetch_new_swaps

    Parameters:
        None

    Return:
        List[dict]:
            New swap rows as dicts ordered oldest-first.
            Only includes swaps from tracked whale wallets.

    Method Description:
        Queries the swaps table for rows with id > _last_seen_swap_id
        whose owner is in the loaded whale targets list. Returns them
        oldest-first so trades are processed in chronological order.
    """
    def _fetch_new_swaps(self) -> List[dict]:
        if self._db_conn is None or not self.targets:
            return []
        try:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                SELECT id, amount_in, price_per_token, timestamp,
                       amount_out, owner, token_out_mint, token_in_mint
                FROM swaps
                WHERE id > %s
                  AND owner = ANY(%s)
                ORDER BY id ASC
                """,
                (self._last_seen_swap_id, self.targets)
            )
            rows = cursor.fetchall()
            cursor.close()

            swaps = []
            for row in rows:
                swaps.append({
                    "id":              row[0],
                    "amount_in":       float(row[1]),
                    "price_per_token": float(row[2]),
                    "timestamp":       row[3],
                    "amount_out":      float(row[4]),
                    "owner":           row[5],
                    "token_out_mint":  row[6],
                    "token_in_mint":   row[7],
                })
            return swaps

        except Exception as e:
            print(f"Database poll error: {e}")
            return []


    # -----------------------------------------------------------------------
    # Price feed
    # -----------------------------------------------------------------------

    """
    Method Name:
        _get_price

    Parameters:
        token_mint (str):
            The on-chain mint address of the token to price.

    Return:
        Optional[float]:
            Current USD price from Jupiter, or None on failure.

    Method Description:
        Calls the Jupiter Price API v3 with the token's mint address
        and returns the current USD price. Used for both PnL tracking
        and sell threshold evaluation.

        Calls the Jupiter Price API v3 with the token's mint address
        and returns the current USD price. Used for both PnL tracking
        and sell threshold evaluation.

        Common spend tokens (SOL, USDC, USDT) are handled by a whitelist
        in executeCopy and never passed here, avoiding Jupiter returning
        null for native mints.
    """

    def _get_price(self, mints: List[str]) -> Dict[str, Optional[float]]:
        """
        Fetches prices for multiple mints.
        Results are cached for the duration of the current poll cycle so
        Jupiter / DexScreener are never called more than once per mint per poll.
        Tries Jupiter first (batch), then falls back to DexScreener
        (per-mint) for any mints Jupiter could not price.
        Returns a dictionary mapping mint address to its USD price.
        """
        if not mints:
            return {}

        # Serve already-fetched prices from the poll-scoped cache
        uncached = [m for m in mints if m not in self._price_cache]

        if uncached:
            fetched: Dict[str, Optional[float]] = {m: None for m in uncached}

            # --- Step 1: Jupiter batch call ---
            try:
                ids_param = ",".join(uncached)
                url = f"https://api.jup.ag/price/v3?ids={ids_param}"
                headers = {
                    "Accept": "application/json",
                    "x-api-key": self._jupiter_api_key,
                }
                response = requests.get(url, headers=headers, timeout=10)

                if response.status_code == 200:
                    data = response.json().get("data", {})
                    for mint in uncached:
                        if mint in data and data[mint]:
                            fetched[mint] = float(data[mint]["price"])
                else:
                    print(f"  [JUPITER ERROR] Status {response.status_code}")

            except Exception as e:
                print(f"  [JUPITER ERROR] {e}")

            # --- Step 2: DexScreener fallback for any mints Jupiter missed ---
            still_missing = [m for m in uncached if fetched[m] is None]
            for mint in still_missing:
                try:
                    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
                    response = requests.get(url, timeout=10)

                    if response.status_code != 200:
                        continue

                    pairs = response.json().get("pairs") or []
                    if not pairs:
                        continue

                    # Pick the pair with the highest liquidity in USD
                    best = max(
                        (p for p in pairs if p.get("priceUsd")),
                        key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
                        default=None,
                    )
                    if best:
                        fetched[mint] = float(best["priceUsd"])
                        print(f"  [DEXSCREENER] Priced {mint[:8]}... at ${fetched[mint]:.8f}")

                except Exception as e:
                    print(f"  [DEXSCREENER ERROR] {mint[:8]}...: {e}")

            # Store all newly fetched results in the poll-scoped cache
            self._price_cache.update(fetched)

        return {m: self._price_cache[m] for m in mints}



    # -----------------------------------------------------------------------
    # Buy side
    # -----------------------------------------------------------------------

    """
    Method Name:
        executeCopy

    Parameters:
        swap (dict):
            A swap row dict from _fetch_new_swaps containing all 8 columns.

    Return:
        bool:
            True if the copy trade executed successfully.
            False if insufficient balance or price unavailable.

    Method Description:
        Mirrors a whale swap detected in the database.

        Position sizing:
            Uses RISK_PER_TRADE * current balance as the USD amount
            to allocate, independent of the whale's actual spend.

        Price:
            Fetches the real-time Jupiter price for both the spend token
            (token_out_mint, e.g. SOL/USDC) and the buy token (token_in_mint).
            The spend token price is checked first — if it cannot be priced
            the swap is skipped. The buy token price drives the entry price;
            falls back to the database price_per_token if Jupiter is unavailable.

        Persistence:
            Saves the updated account balance and new/updated position
            to the database. Logs the trade to paper_trades.
    """
    def executeCopy(self, swap: dict) -> bool:
        # token_in_mint  = the token being BOUGHT (received by the whale)
        # token_out_mint = the token being SPENT  (e.g. SOL/USDC paid by the whale)
        token_mint      = swap["token_in_mint"]
        spend_mint      = swap["token_out_mint"]
        token_symbol    = token_mint
        wallet_address  = swap["owner"]

        amount_usd = self.balance * RISK_PER_TRADE

        if amount_usd > self.balance:
            print(f"Insufficient balance to copy swap for {token_mint}")
            return False

        # Check the spend token is a known trusted mint (e.g. SOL, USDC, USDT).
        # We whitelist these rather than pricing them via Jupiter because Jupiter
        # can return null for native SOL and stable mints in some API tiers.
        TRUSTED_SPEND_MINTS = {
            "So11111111111111111111111111111111111111112",   # Native SOL
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
        }
        if spend_mint not in TRUSTED_SPEND_MINTS:
            prices = self._get_price([spend_mint, token_mint])
            price_spend = prices.get(spend_mint)
            if price_spend is None:
                print(
                    f"  [SKIP] Could not fetch price for spend mint {spend_mint}. "
                    f"Skipping copy of swap for {token_mint}."
                )
                return False
            price = prices.get(token_mint)
        else:
            price_spend = None  # trusted mint, no price check needed
            prices = self._get_price([token_mint])
            price = prices.get(token_mint)

        # Fetch price of the token we intend to buy.
        if price is None:
            print(f"  Jupiter price unavailable for {token_mint}, using DB price.")
            price = swap["price_per_token"]

        slipped_price = price * 1.02
        tokens_bought = amount_usd / slipped_price
        self.balance -= amount_usd
        now = datetime.now(timezone.utc)

        if token_mint in self.positions:
            existing = self.positions[token_mint]
            total_tokens = existing["amount"] + tokens_bought
            avg_price = (
                (existing["entry_price"] * existing["amount"]) +
                (slipped_price * tokens_bought)
            ) / total_tokens
            existing["amount"]      = total_tokens
            existing["entry_price"] = avg_price
            existing["peak_price"]  = max(existing["peak_price"], slipped_price)
            existing["cost_basis"] += amount_usd
        else:
            self.positions[token_mint] = {
                "token_out_mint": token_mint,
                "token_symbol":   token_symbol,
                "amount":         tokens_bought,
                "entry_price":    slipped_price,
                "peak_price":     slipped_price,
                "entry_time":     now,
                "cost_basis":     amount_usd,
                "wallet_address": wallet_address,
            }

        self.tradeHistory.append(
            Trade(token_symbol, 'BUY', slipped_price, tokens_bought, now)
        )

        # Persist
        self._save_account()
        self._save_position(token_mint)
        self._log_trade(
            wallet_address=wallet_address,
            token_out_mint=token_mint,
            token_symbol=token_symbol,
            side='BUY',
            price=slipped_price,
            amount=tokens_bought,
            usd_value=amount_usd,
        )

        spend_price_str = f"${price_spend:.6f}" if price_spend is not None else "trusted"
        print(
            f"  [BUY] {token_symbol} | "
            f"Whale: {wallet_address[:8]}... | "
            f"Spent ${amount_usd:.2f} | "
            f"SpendMint ({spend_mint[:8]}...) {spend_price_str} | "
            f"Price ${slipped_price:.6f} | "
            f"Tokens {tokens_bought:.4f} | "
            f"Balance ${self.balance:.2f}"
        )
        return True


    # -----------------------------------------------------------------------
    # Sell side
    # -----------------------------------------------------------------------

    """
    Method Name:
        evaluateSells

    Parameters:
        None

    Return:
        None

    Method Description:
        Iterates over all open positions and checks two sell conditions
        against the current real-time Jupiter price:

        1. Trailing Stop:
               If the current price has dropped more than TRAILING_STOP_PCT
               below the position's peak price, sell immediately.
               The peak price is updated and persisted if price has risen.

        2. Time-Based Exit:
               If the position has been held longer than MAX_HOLD_SECONDS,
               sell regardless of price action.
    """
    def evaluateSells(self):
        now = datetime.now(timezone.utc)
        mints_to_sell = []

        # Fetch all open position prices in a single batch API call
        open_mints = list(self.positions.keys())
        prices = self._get_price(open_mints) if open_mints else {}

        for token_mint, pos in list(self.positions.items()):
            current_price = prices.get(token_mint)

            if current_price is None:
                # Fall back to entry_price so time-based exits still fire.
                # Trailing stop won't trigger at entry price (peak == entry),
                # but the position won't be stuck open forever.
                current_price = pos["entry_price"]
                print(
                    f"  [SELL CHECK] Could not fetch price for {token_mint}, "
                    f"using entry price ${current_price:.6f} for exit evaluation."
                )

            # Update and persist peak price if price has risen
            if current_price > pos["peak_price"]:
                pos["peak_price"] = current_price
                self._save_position(token_mint)

            # --- Trailing Stop ---
            trailing_stop_price = pos["peak_price"] * (1 - TRAILING_STOP_PCT)
            if current_price <= trailing_stop_price:
                print(
                    f"  [TRAILING STOP] {pos['token_symbol']} | "
                    f"Peak ${pos['peak_price']:.6f} | "
                    f"Current ${current_price:.6f} | "
                    f"Stop ${trailing_stop_price:.6f}"
                )
                mints_to_sell.append((token_mint, current_price, "TRAILING_STOP"))
                continue

            # --- Time-Based Exit ---
            entry_time = pos["entry_time"]
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
            held_seconds = (now - entry_time).total_seconds()

            if held_seconds >= MAX_HOLD_SECONDS:
                print(
                    f"  [TIME EXIT] {pos['token_symbol']} | "
                    f"Held {held_seconds / 60:.1f} min | "
                    f"Current ${current_price:.6f}"
                )
                mints_to_sell.append((token_mint, current_price, "TIME_EXIT"))

        for token_mint, price, reason in mints_to_sell:
            self._sellPosition(token_mint, price, reason)


    """
    Method Name:
        _sellPosition

    Parameters:
        token_mint (str):
            Mint address of the token to sell.
        price (float):
            Current market price to sell at.
        reason (str):
            Label for why the sell was triggered.

    Return:
        None

    Method Description:
        Executes a full exit of an open position.

        - Applies 2% sell slippage.
        - Credits proceeds to balance.
        - Removes position from memory and database.
        - Logs the trade to paper_trades.
        - Updates the originating whale wallet's performance stats.
        - Persists the updated account balance.
    """
    def _sellPosition(self, token_mint: str, price: float, reason: str):
        if token_mint not in self.positions:
            return

        pos = self.positions[token_mint]
        amount = pos["amount"]
        token_symbol = pos["token_symbol"]
        wallet_address = pos["wallet_address"]

        slipped_price = price * 0.98
        proceeds = amount * slipped_price
        realised_pnl = proceeds - pos["cost_basis"]

        self.balance += proceeds
        del self.positions[token_mint]
        now = datetime.now(timezone.utc)

        self.tradeHistory.append(
            Trade(token_symbol, 'SELL', slipped_price, amount, now)
        )

        # Persist
        self._delete_position(token_mint)
        self._save_account()
        self._log_trade(
            wallet_address=wallet_address,
            token_out_mint=token_mint,
            token_symbol=token_symbol,
            side='SELL',
            price=slipped_price,
            amount=amount,
            usd_value=proceeds,
            sell_reason=reason,
            realised_pnl=realised_pnl,
        )
        self._update_trader_performance(wallet_address, realised_pnl)

        print(
            f"  [SELL] {token_symbol} | "
            f"Reason: {reason} | "
            f"Price ${slipped_price:.6f} | "
            f"Proceeds ${proceeds:.2f} | "
            f"Realised PnL ${realised_pnl:+.2f} | "
            f"Balance ${self.balance:.2f}"
        )


    # -----------------------------------------------------------------------
    # Main poll loop
    # -----------------------------------------------------------------------

    """
    Method Name:
        run

    Parameters:
        None

    Return:
        None

    Method Description:
        The main engine loop. On each iteration:

        1. Fetches new swap rows for tracked whale wallets (buy side).
        2. Calls executeCopy for each new swap.
        3. Updates _last_seen_swap_id to avoid reprocessing.
        4. Calls evaluateSells to check all open positions (sell side).
        5. Prints a portfolio snapshot.
        6. Sleeps for POLL_INTERVAL_SECONDS before repeating.
    """
    def run(self):
        print(f"\nPaper Trading Engine started. Polling every {POLL_INTERVAL_SECONDS}s.\n")
        try:
            while True:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] --- Poll ---")
                self._price_cache.clear()

                # Buy side — check for new whale swaps
                new_swaps = self._fetch_new_swaps()
                if new_swaps:
                    for swap in new_swaps:
                        print(
                            f"  [NEW SWAP] ID={swap['id']} | "
                            f"Owner={swap['owner'][:8]}... | "
                            f"Mint={swap['token_out_mint']}"
                        )
                        self.executeCopy(swap)
                    self._last_seen_swap_id = new_swaps[-1]["id"]
                else:
                    print("  No new swaps.")

                # Sell side — evaluate open positions
                if self.positions:
                    self.evaluateSells()

                # Portfolio snapshot
                portfolio_val = self.getPortfolioValue()
                pnl = self.getPnL()
                print(
                    f"  Portfolio: ${portfolio_val:.2f} | "
                    f"Cash: ${self.balance:.2f} | "
                    f"PnL: ${pnl:+.2f} | "
                    f"Open positions: {len(self.positions)}\n"
                )

                time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\nPaper Trading Engine shutting down...")
            self.close()


    # -----------------------------------------------------------------------
    # Portfolio metrics
    # -----------------------------------------------------------------------

    """
    Method Name:
        getPortfolioValue

    Parameters:
        None

    Return:
        float:
            Total portfolio value (cash + open positions at live prices).

    Method Description:
        Fetches real-time Jupiter prices for all open positions and
        sums their market value with the current cash balance.
    """
    def getPortfolioValue(self) -> float:
        total = self.balance
        if not self.positions:
            return total
        open_mints = list(self.positions.keys())
        prices = self._get_price(open_mints)
        for token_mint, pos in self.positions.items():
            price = prices.get(token_mint)
            if price is None:
                # Fall back to entry_price so portfolio value is never understated
                price = pos["entry_price"]
            total += pos["amount"] * price
        return total


    """
    Method Name:
        getPnL

    Parameters:
        None

    Return:
        float:
            Profit or loss relative to initial balance.

    Method Description:
        Subtracts the initial balance from the current portfolio value.
    """
    def getPnL(self) -> float:
        return self.getPortfolioValue() - self.initialBalance


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
        Dict[str, dict]:
            Dictionary of open positions keyed by token_out_mint.

    Method Description:
        Returns the current open positions in the account.
    """
    def getPositions(self) -> Dict[str, dict]:
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
    """
    def close(self):
        if self._db_conn:
            self._db_conn.close()
            print("Database connection closed.")


if __name__ == "__main__":
    account = PaperAccount(initialBalance=10000.0)
    account.run()