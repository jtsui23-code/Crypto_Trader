import os
import json
import time
import requests
import psycopg2
import itertools
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Optional
from datetime import datetime, timezone
import requests
import threading
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from discord_notifier import send_discord_alert_sync

load_dotenv()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# How often the engine polls the swaps table for new whale trades (seconds)
POLL_INTERVAL_SECONDS = 3

# Fraction of current balance to risk on each copied trade (e.g. 0.05 = 5%)
RISK_PER_TRADE = 0.05

# --- Take Profit (Split A) ---
# Sell this fraction of the position when price rises TAKE_PROFIT_PCT above entry.
# e.g. 0.50 = sell 50% of tokens when price is up 50% from entry.
TAKE_PROFIT_PCT   = 0.2   # Gain threshold that triggers the partial exit (50%)
TAKE_PROFIT_SPLIT = 0.7   # Fraction of the position to sell at the TP target  (50%)

# --- Trailing Stop (Split B) ---
# Applied to the remaining tokens after the TP split has fired (or to the full
# position if TP has not triggered yet).
# How far the price can drop from the position's peak before selling (e.g. 0.20 = 20%)
TRAILING_STOP_PCT = 0.35

# --- Hard Stop-Loss ---
# Sell the ENTIRE remaining position immediately if price drops this far below entry.
# e.g. 0.15 = exit at a 15% loss from entry price.
STOP_LOSS_PCT = 0.15

# --- Time-Based Exit ---
# Maximum time to hold a position before force-selling (seconds)
MAX_HOLD_SECONDS = 70  # 3 minutes

# ---------------------------------------------------------------------------
# Other sell thresholds available for future experimentation (not yet active)
# ---------------------------------------------------------------------------
# MAX_ALLOCATION_PCT    = 0.30   # Trim position if it grows beyond X% of portfolio
# VOLUME_DROP_EXIT      = True   # Sell if 5-min volume drops sharply (needs price API extension)
# WHALE_EXIT_MIRROR     = True   # Sell when the whale sells the same token (full copy)

# Load any previously saved config overrides from data/config.json so we can
_CONFIG_FILE = Path(__file__).parent.parent / "data" / "config.json"
if _CONFIG_FILE.exists():
    try:
        with open(_CONFIG_FILE, 'r') as f:
            _saved = json.load(f)
            RISK_PER_TRADE = _saved.get("risk_per_trade", RISK_PER_TRADE)
            TAKE_PROFIT_PCT = _saved.get("take_profit_pct", TAKE_PROFIT_PCT)
            TAKE_PROFIT_SPLIT = _saved.get("take_profit_split", TAKE_PROFIT_SPLIT)
            TRAILING_STOP_PCT = _saved.get("trailing_stop_pct", TRAILING_STOP_PCT)
            STOP_LOSS_PCT = _saved.get("stop_loss_pct", STOP_LOSS_PCT)
            MAX_HOLD_SECONDS = _saved.get("max_hold_seconds", MAX_HOLD_SECONDS)
    except Exception as e:
        print(f"Error loading persistent config: {e}")

# ---------------------------------------------------------------------------
# Configuration Testing Mode
# ---------------------------------------------------------------------------
# Set CONFIG_TEST_MODE = True to iterate through every permutation of the
# parameter grids below automatically. The engine runs SAMPLE_SIZE completed
# sell trades per permutation, logs PnL, then resets and moves to the next.
# Set CONFIG_TEST_MODE = False to run indefinitely with the defaults above.
# ---------------------------------------------------------------------------

CONFIG_TEST_MODE = False  # <-- Toggle this flag to enable/disable config testing

# Number of completed sell trades required before rotating to the next config.
SAMPLE_SIZE = 100

# ---------------------------------------------------------------------------
# Parameter grids — add/remove values freely.
# Every combination is seeded into the config_test_runs table in Neon on
# first run, then the bot queries for the next untested row (pnl IS NULL).
# Counting by 3 to keep the total combination count manageable.
# Order: [RISK_PER_TRADE, TAKE_PROFIT_PCT, TAKE_PROFIT_SPLIT,
#         TRAILING_STOP_PCT, STOP_LOSS_PCT, MAX_HOLD_SECONDS]
# ---------------------------------------------------------------------------
_PARAM_GRID = (
    # RISK_PER_TRADE — 3% to 10%, step 3
    [round(x * 0.01, 2) for x in range(3, 11, 3)],
    # Result: [0.03, 0.06, 0.09]

    # TAKE_PROFIT_PCT — 10% to 49%, step 3
    [round(x * 0.01, 2) for x in range(10, 50, 3)],
    # Result: [0.1, 0.13, 0.16, 0.19, 0.22, 0.25, 0.28, 0.31, 0.34, 0.37, 0.4, 0.43, 0.46, 0.49]

    # TAKE_PROFIT_SPLIT — 20% to 77%, step 3
    [round(x * 0.01, 2) for x in range(20, 78, 3)],
    # Result: [0.2, 0.23, 0.26, ..., 0.77]

    # TRAILING_STOP_PCT — 20% to 50%, step 3
    [round(x * 0.01, 2) for x in range(20, 51, 3)],
    # Result: [0.2, 0.23, 0.26, ..., 0.5]

    # STOP_LOSS_PCT — 10% to 40%, step 3
    [round(x * 0.01, 2) for x in range(10, 41, 3)],
    # Result: [0.1, 0.13, 0.16, ..., 0.4]

    # MAX_HOLD_SECONDS — maximum hold time before forced exit
    [60, 120, 180],
)


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
            amount          - quantity of tokens currently held
            entry_price     - average price paid per token (after slippage)
            peak_price      - highest price seen since entry
            entry_time      - datetime the position was opened
            cost_basis      - total USD spent on the position
            wallet_address  - whale wallet that triggered the buy
            tp_sold         - True once the TAKE_PROFIT_SPLIT partial exit has fired
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
    def __init__(self, initialBalance: float = 10000.0, reset:bool = False, generate_config: bool = True):
        self.initialBalance = initialBalance
        self.balance = initialBalance
        self.positions: Dict[str, dict] = {}
        self.tradeHistory: List[Trade] = []
        self.targets: list = []
        self.reload_requested = False

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
        # Trade counter and configuration testing state
        # -----------------------------------------------------------------------
        # Counts completed sell events (full or partial) in the current config run.
        self.trade_count: int = 0

        # ID of the config_test_runs row currently being tested.
        # None when CONFIG_TEST_MODE is False.
        self._current_config_id:  Optional[int]  = None
        self._current_config_row: Optional[dict] = None

        # Seed the config table and load the first untested config from Neon.
        if CONFIG_TEST_MODE:
            self._seed_config_table(seed=generate_config)
            next_config = self._fetch_next_config()
            if next_config is None:
                print("[CONFIG TEST] All configurations already tested. Nothing to run.")
                self.close()
                raise SystemExit(0)
            self._apply_config_row(next_config)

        if reset:
            self.reset_portfolio()


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

                    clean = [w.strip() for w in data if isinstance(w, str) and w.strip()]
                    print(f"Loaded {len(clean)} whale targets.")
                    return clean
            else:
                print(f"Warning: {file_path} not found.")
                return []

        except Exception as e:
            print(f"Error reading whales.json: {e}")
            return []
        


    """
    Method Name:
        reset_portfolio

    Parameters:
        newBalance (float):
            The balance to reset the account to. Defaults to the
            original initialBalance set at construction time.

    Return:
        None

    Method Description:
        Resets the paper trading account to a clean state.

        - Force-closes all open positions without executing sells or
        updating trader performance stats.
        - Wipes the in-memory trade history.
        - Restores the cash balance to newBalance (defaults to initialBalance).
        - Clears all rows from paper_positions in the database.
        - Persists the reset balance to paper_account.
        - Resets _last_seen_swap_id to the current max swap ID so the
        engine does not replay old swaps after the reset.
    """
    def reset_portfolio(self, newBalance: float = None):
        print("\nResetting portfolio to a clean state...")

        if newBalance is None:
            newBalance = self.initialBalance

        # Clear in-memory state
        self.positions.clear()
        self.tradeHistory.clear()
        self.balance = newBalance
        self.initialBalance = newBalance

        # Wipe open positions from the database
        if self._db_conn is not None:
            try:
                cursor = self._db_conn.cursor()
                cursor.execute("DELETE FROM paper_positions")
                cursor.execute("DELETE FROM paper_trades")
                cursor.execute("DELETE FROM paper_trader_performance")
                cursor.execute("DELETE FROM swaps")
                cursor.close()
                
                # Re-seed the performance table with zeroed-out rows for current targets
                self._ensure_trader_performance_rows()
            except Exception as e:
                print(f"Error clearing tables during reset: {e}")

        # Persist the reset balance
        self._save_account()

        # Advance the swap cursor so stale swaps are not replayed
        self._last_seen_swap_id = self._get_max_swap_id()
        self.trade_count = 0

        self.reload_requested = True

        print(f"Portfolio reset. Balance restored to ${self.balance:.2f}.")

        # Notify the API to refresh its state and broadcast the cleared positions
        try:
            requests.post("http://api:8000/api/internal/trigger/summary", timeout=1)
            requests.post("http://api:8000/api/internal/trigger/traders", timeout=1)
            requests.post("http://api:8000/api/internal/broadcast/positions", json={"positions": []}, timeout=1)

            requests.post("http://api:8000/api/internal/broadcast/live_feed", json={"clear": True}, timeout=1)
        except Exception as e:
            pass


    # -----------------------------------------------------------------------
    # Configuration testing helpers
    # -----------------------------------------------------------------------

    """
    Method Name:
        _apply_config

    Parameters:
        index (int):
            Index into TRADING_CONFIGS to apply.

    Return:
        None

    Method Description:
        Overwrites the module-level trading constants with the values from
        TRADING_CONFIGS[index]. This allows the engine to test different
        strategy parameters without restarting.
    """
    def _apply_config(self, index: int):
        """
        Method Name:
            _apply_config

        Parameters:
            index (int):
                Legacy parameter kept for compatibility with __init__
                during the initial seed call. Applies the config stored
                in self._current_config_row.

        Return:
            None

        Method Description:
            Thin wrapper that delegates to _apply_config_row using the
            already-loaded _current_config_row. Called from __init__ after
            _fetch_next_config has populated _current_config_row.
        """
        if hasattr(self, "_current_config_row") and self._current_config_row:
            self._apply_config_row(self._current_config_row)


    def _apply_config_row(self, row: dict):
        """
        Method Name:
            _apply_config_row

        Parameters:
            row (dict):
                A config_test_runs row dict with keys:
                id, risk_per_trade, take_profit_pct, take_profit_split,
                trailing_stop_pct, stop_loss_pct, max_hold_seconds,
                tested_count, total_count.

        Return:
            None

        Method Description:
            Overwrites the module-level trading constants with values from
            the supplied DB row and updates _current_config_id /
            _current_config_row so _log_config_result knows which row to
            update when the run completes.
        """
        global RISK_PER_TRADE, TAKE_PROFIT_PCT, TAKE_PROFIT_SPLIT
        global TRAILING_STOP_PCT, STOP_LOSS_PCT, MAX_HOLD_SECONDS

        self._current_config_id  = row["id"]
        self._current_config_row = row

        RISK_PER_TRADE    = row["risk_per_trade"]
        TAKE_PROFIT_PCT   = row["take_profit_pct"]
        TAKE_PROFIT_SPLIT = row["take_profit_split"]
        TRAILING_STOP_PCT = row["trailing_stop_pct"]
        STOP_LOSS_PCT     = row["stop_loss_pct"]
        MAX_HOLD_SECONDS  = row["max_hold_seconds"]

        tested = self._count_tested_configs()
        total  = self._count_total_configs()

        print(
            f"\n{'='*60}\n"
            f"[CONFIG TEST] Loaded config id={self._current_config_id} "
            f"({tested}/{total} done)\n"
            f"  risk={RISK_PER_TRADE} | tp={TAKE_PROFIT_PCT} | "
            f"tp_split={TAKE_PROFIT_SPLIT} | ts={TRAILING_STOP_PCT} | "
            f"sl={STOP_LOSS_PCT} | hold={MAX_HOLD_SECONDS}s\n"
            f"{'='*60}\n"
        )


    """
    Method Name:
        _log_config_result

    Parameters:
        config_name (str):
            Human-readable name of the config that just completed.
        pnl (float):
            Realised PnL for this config run.
        trade_count (int):
            Number of completed sell trades in this run.
        start_balance (float):
            Portfolio balance at the start of this config run.
        end_balance (float):
            Portfolio balance at the end of this config run.

    Return:
        None

    Method Description:
        Appends a result record to config_test_results.json.
        Each record captures the config parameters, PnL, trade
        count, and timestamps so results persist across runs.
    """
    def _log_config_result(
        self,
        pnl: float,
        trade_count: int,
        start_balance: float,
        end_balance: float,
    ):
        """
        Method Name:
            _log_config_result

        Parameters:
            pnl (float):
                Realised PnL for this config run.
            trade_count (int):
                Number of completed sell trades in this run.
            start_balance (float):
                Portfolio balance at the start of this config run.
            end_balance (float):
                Portfolio balance at the end of this config run.

        Return:
            None

        Method Description:
            Writes the completed config's PnL result back to the
            config_test_runs row in Neon (identified by _current_config_id).
            A row with pnl IS NOT NULL is considered fully tested and will
            be skipped when the bot resumes after a restart.
        """
        if self._db_conn is None or self._current_config_id is None:
            return

        pnl_pct = round((pnl / start_balance) * 100, 4) if start_balance else 0

        try:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                UPDATE config_test_runs
                SET pnl            = %s,
                    pnl_pct        = %s,
                    end_balance    = %s,
                    sample_size    = %s,
                    completed_at   = NOW()
                WHERE id = %s
                """,
                (round(pnl, 4), pnl_pct, round(end_balance, 4),
                 trade_count, self._current_config_id)
            )
            cursor.close()
            print(
                f"[CONFIG TEST] Result saved to DB — row id={self._current_config_id} | "
                f"PnL ${pnl:+.2f} ({pnl_pct:+.2f}%) over {trade_count} trades."
            )
        except Exception as e:
            print(f"[CONFIG TEST] Warning: Could not save result to DB: {e}")


    """
    Method Name:
        _rotate_config

    Parameters:
        None

    Return:
        None

    Method Description:
        Called when trade_count reaches SAMPLE_SIZE.

        1. Snapshots current PnL and logs the result to JSON.
        2. Resets the portfolio and trade counter.
        3. Advances _config_index to the next config.
        4. Applies the new config, or prints a completion summary
           and exits if all configs have been tested.
    """
    def _rotate_config(self):
        """
        Method Name:
            _rotate_config

        Parameters:
            None

        Return:
            None

        Method Description:
            Called when trade_count reaches SAMPLE_SIZE.

            1. Snapshots current PnL and writes the result to the
               config_test_runs row in Neon via _log_config_result.
            2. Resets the portfolio and trade counter.
            3. Queries for the next untested config row (pnl IS NULL)
               ordered by id, applies it, or prints a completion summary
               and exits if all configs have been tested.
        """
        start_balance = self.initialBalance
        end_balance   = self.getPortfolioValue()
        pnl           = end_balance - start_balance

        tested_count  = self._count_tested_configs()
        total_count   = self._count_total_configs()

        print(
            f"\n{'='*20}\n"
            f"[CONFIG TEST] Config id={self._current_config_id} completed {SAMPLE_SIZE} trades.\n"
            f"  Start: ${start_balance:.2f} | End: ${end_balance:.2f} | "
            f"PnL: ${pnl:+.2f}\n"
            f"  Progress: {tested_count}/{total_count} configs done.\n"
            f"{'='*20}"
        )

        self._log_config_result(
            pnl=pnl,
            trade_count=self.trade_count,
            start_balance=start_balance,
            end_balance=end_balance,
        )

        self.trade_count = 0

        # Load the next untested config from the DB
        next_config = self._fetch_next_config()
        if next_config is None:
            self._print_test_summary()
            print("[CONFIG TEST] All configurations tested. Shutting down.")
            self.close()
            raise SystemExit(0)

        # Reset portfolio and apply the next config
        self.reset_portfolio(newBalance=self.initialBalance)
        self._apply_config_row(next_config)


    def _count_tested_configs(self) -> int:
        """Returns the number of config_test_runs rows where pnl IS NOT NULL."""
        if self._db_conn is None:
            return 0
        try:
            cursor = self._db_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM config_test_runs WHERE pnl IS NOT NULL")
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else 0
        except Exception:
            return 0


    def _count_total_configs(self) -> int:
        """Returns the total number of rows in config_test_runs."""
        if self._db_conn is None:
            return 0
        try:
            cursor = self._db_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM config_test_runs")
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else 0
        except Exception:
            return 0


    """
    Method Name:
        _print_test_summary

    Parameters:
        None

    Return:
        None

    Method Description:
        Reads config_test_results.json and prints a ranked summary
        table of all completed configuration runs sorted by PnL.
    """
    def _print_test_summary(self):
        """
        Method Name:
            _print_test_summary

        Parameters:
            None

        Return:
            None

        Method Description:
            Reads all completed config rows (pnl IS NOT NULL) from
            config_test_runs in Neon and prints a ranked summary table
            sorted by PnL descending.
        """
        print(f"\n{'='*20}")
        print("[CONFIG TEST] ===== FINAL RESULTS SUMMARY =====")

        if self._db_conn is None:
            print("  No database connection — cannot read results.")
            return

        try:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                SELECT id, risk_per_trade, take_profit_pct, take_profit_split,
                       trailing_stop_pct, stop_loss_pct, max_hold_seconds,
                       pnl, pnl_pct, sample_size
                FROM config_test_runs
                WHERE pnl IS NOT NULL
                ORDER BY pnl DESC
                """
            )
            rows = cursor.fetchall()
            cursor.close()
        except Exception as e:
            print(f"  Could not read results from DB: {e}")
            return

        if not rows:
            print("  No completed configs found.")
            return

        print(
            f"  {'Rank':<5} {'ID':<6} {'Risk':>6} {'TP%':>6} "
            f"{'Split':>6} {'TS%':>6} {'SL%':>6} {'Hold':>6} "
            f"{'PnL':>10} {'PnL%':>8} {'Trades':>7}"
        )
        print(f"  {'-'*80}")
        for i, r in enumerate(rows, 1):
            (cfg_id, risk, tp_pct, tp_split, ts_pct, sl_pct,
             hold_s, pnl, pnl_pct, sample_size) = r
            print(
                f"  {i:<5} {cfg_id:<6} "
                f"{risk:>6.2f} {tp_pct:>6.2f} {tp_split:>6.2f} "
                f"{ts_pct:>6.2f} {sl_pct:>6.2f} {hold_s:>6} "
                f"${pnl:>+9.2f} {pnl_pct:>+7.2f}% {sample_size:>7}"
            )
        print(f"{'='*20}\n")



    def _seed_config_table(self, seed:bool = True):
        """
        Method Name:
            _seed_config_table

        Parameters:
            seed: Bool - Decides if needing to generate a new config table. This is skipped once a config table is 
                         genearted through setting seed to False.

        Return:
            None

        Method Description:
            Generates every permutation from _PARAM_GRID and inserts them
            into config_test_runs using INSERT ... ON CONFLICT DO NOTHING.
            Safe to call on every startup — already-existing rows (matched
            on the unique constraint across all 6 param columns) are skipped,
            so re-seeding never overwrites pnl results from completed runs.

            Also creates the table if it does not yet exist.
        """
        if self._db_conn is None:
            return

        try:
            if seed:
                print("seeding")
                cursor = self._db_conn.cursor()

                # Create table if it doesn't exist yet
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS config_test_runs (
                        id                 SERIAL PRIMARY KEY,
                        risk_per_trade     NUMERIC(6,4) NOT NULL,
                        take_profit_pct    NUMERIC(6,4) NOT NULL,
                        take_profit_split  NUMERIC(6,4) NOT NULL,
                        trailing_stop_pct  NUMERIC(6,4) NOT NULL,
                        stop_loss_pct      NUMERIC(6,4) NOT NULL,
                        max_hold_seconds   INTEGER       NOT NULL,
                        pnl                NUMERIC(12,4),
                        pnl_pct            NUMERIC(10,4),
                        end_balance        NUMERIC(12,4),
                        sample_size        INTEGER,
                        created_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
                        completed_at       TIMESTAMPTZ,
                        UNIQUE (risk_per_trade, take_profit_pct, take_profit_split,
                                trailing_stop_pct, stop_loss_pct, max_hold_seconds)
                    )
                    """
                )

                # Generate and insert all permutations
                all_configs = list(itertools.product(*_PARAM_GRID))
                inserted = 0
                for cfg in all_configs:
                    risk, tp_pct, tp_split, ts_pct, sl_pct, hold_s = cfg
                    cursor.execute(
                        """
                        INSERT INTO config_test_runs
                            (risk_per_trade, take_profit_pct, take_profit_split,
                            trailing_stop_pct, stop_loss_pct, max_hold_seconds)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (risk_per_trade, take_profit_pct, take_profit_split,
                                    trailing_stop_pct, stop_loss_pct, max_hold_seconds)
                        DO NOTHING
                        """,
                        (risk, tp_pct, tp_split, ts_pct, sl_pct, hold_s)
                    )
                    inserted += cursor.rowcount

                cursor.close()
                total = len(all_configs)
                print(
                    f"[CONFIG TEST] Config table seeded — "
                    f"{inserted} new rows added, {total - inserted} already existed "
                    f"({total} total permutations)."
                )

        except Exception as e:
            print(f"[CONFIG TEST] Error seeding config table: {e}")


    def _fetch_next_config(self) -> Optional[dict]:
        """
        Method Name:
            _fetch_next_config

        Parameters:
            None

        Return:
            dict | None:
                The next untested config row as a dict, or None if all
                configs have been tested (pnl is set on every row).

        Method Description:
            Queries config_test_runs for the lowest id row where pnl IS NULL,
            indicating it has not yet been fully tested. This is how the bot
            resumes from exactly where it left off after a restart — any row
            without a pnl score is fair game, any row with a score is skipped.
        """
        if self._db_conn is None:
            return None

        try:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                SELECT id, risk_per_trade, take_profit_pct, take_profit_split,
                       trailing_stop_pct, stop_loss_pct, max_hold_seconds
                FROM config_test_runs
                WHERE pnl IS NULL
                ORDER BY id ASC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            cursor.close()

            if row is None:
                return None

            return {
                "id":                row[0],
                "risk_per_trade":    float(row[1]),
                "take_profit_pct":   float(row[2]),
                "take_profit_split": float(row[3]),
                "trailing_stop_pct": float(row[4]),
                "stop_loss_pct":     float(row[5]),
                "max_hold_seconds":  int(row[6]),
            }

        except Exception as e:
            print(f"[CONFIG TEST] Error fetching next config: {e}")
            return None


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
                    "tp_sold":        False,  # conservatively reset on restart
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

            try:
                requests.post("http://api:8000/api/internal/trigger/traders", timeout=1)
            except Exception as e:
                pass
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

            # Normalise all target addresses (strip whitespace) so they match
            # the on-chain pubkey strings stored by the decoder exactly.
            clean_targets = [t.strip() for t in self.targets if t and t.strip()]
            if not clean_targets:
                return []

            # Use IN with an explicit tuple rather than ANY(%s) to avoid
            # psycopg2 array-casting issues that silently return zero rows.
            placeholders = ",".join(["%s"] * len(clean_targets))
            cursor.execute(
                f"""
                SELECT id, amount_in, price_per_token, timestamp,
                       amount_out, owner, token_out_mint, token_in_mint
                FROM swaps
                WHERE id > %s
                  AND owner IN ({placeholders})
                ORDER BY id ASC
                """,
                (self._last_seen_swap_id, *clean_targets)
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
            print(f"  [SKIP] Jupiter/DexScreener price unavailable for {token_mint}. Skipping copy.")
            return False

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
            # tp_sold is intentionally preserved — a TP that already fired on
            # the old tokens does not reset just because we averaged in.
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
                "tp_sold":        False,
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

        send_discord_alert_sync(
            f"🟢 **BUY** `{token_symbol[:20]}`\n"
            f"Whale: `{wallet_address[:8]}...`\n"
            f"Spent: **${amount_usd:.2f}** @ ${slipped_price:.6f}\n"
            f"Balance: ${self.balance:.2f}"
        )


        self._broadcast_updates({
            "symbol": token_symbol,
            "side": "BUY",
            "price": slipped_price,
            "amount": tokens_bought,
            "usd_value": amount_usd,
            "sell_reason": None,
            "realised_pnl": None,
            "timestamp": now.isoformat(),
            "wallet_address": wallet_address
        })
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
        Iterates over all open positions and checks sell conditions in
        priority order against the current real-time Jupiter price:

        1. Hard Stop-Loss (full exit):
               If the current price is more than STOP_LOSS_PCT below the
               position's entry price, sell the entire remaining position
               immediately regardless of any other condition.

        2. Take Profit — Split A (partial exit):
               If the current price is at least TAKE_PROFIT_PCT above entry
               AND the TP split has not yet fired (tp_sold == False), sell
               TAKE_PROFIT_SPLIT of the current token balance at market.
               Sets tp_sold = True so this fires only once per position.

        3. Trailing Stop — Split B (full exit of remainder):
               If the current price has dropped more than TRAILING_STOP_PCT
               below the position's peak price, sell whatever tokens remain.
               The peak price is updated and persisted whenever price rises.

        4. Time-Based Exit (full exit):
               If the position has been held longer than MAX_HOLD_SECONDS,
               sell the entire remaining position regardless of price action.
    """
    def evaluateSells(self):
        now = datetime.now(timezone.utc)
        partial_sells = []   # (token_mint, price, fraction, reason)
        full_sells    = []   # (token_mint, price, reason)

        # Fetch all open position prices in a single batch API call
        open_mints = list(self.positions.keys())
        prices = self._get_price(open_mints) if open_mints else {}

        for token_mint, pos in list(self.positions.items()):
            current_price = prices.get(token_mint)

            if current_price is None:
                # Fall back to entry_price so time-based exits still fire.
                current_price = pos["entry_price"]
                print(
                    f"  [SELL CHECK] Could not fetch price for {token_mint}, "
                    f"using entry price ${current_price:.6f} for exit evaluation."
                )

            # Update and persist peak price if price has risen
            if current_price > pos["peak_price"]:
                pos["peak_price"] = current_price
                self._save_position(token_mint)

            # --- 1. Hard Stop-Loss (full exit) ---
            stop_loss_price = pos["entry_price"] * (1 - STOP_LOSS_PCT)
            if current_price <= stop_loss_price:
                print(
                    f"  [STOP LOSS] {pos['token_symbol']} | "
                    f"Entry ${pos['entry_price']:.6f} | "
                    f"Current ${current_price:.6f} | "
                    f"Stop ${stop_loss_price:.6f}"
                )
                full_sells.append((token_mint, current_price, "STOP_LOSS"))
                continue

            # --- 2. Take Profit — Split A (partial exit, fires once) ---
            if not pos["tp_sold"]:
                take_profit_price = pos["entry_price"] * (1 + TAKE_PROFIT_PCT)
                if current_price >= take_profit_price:
                    print(
                        f"  [TAKE PROFIT] {pos['token_symbol']} | "
                        f"Entry ${pos['entry_price']:.6f} | "
                        f"Current ${current_price:.6f} | "
                        f"Target ${take_profit_price:.6f} | "
                        f"Selling {TAKE_PROFIT_SPLIT*100:.0f}% of position"
                    )
                    partial_sells.append((token_mint, current_price, TAKE_PROFIT_SPLIT, "TAKE_PROFIT"))
                    continue

            # --- 3. Trailing Stop — Split B (full exit of remaining tokens) ---
            trailing_stop_price = pos["peak_price"] * (1 - TRAILING_STOP_PCT)
            if current_price <= trailing_stop_price:
                print(
                    f"  [TRAILING STOP] {pos['token_symbol']} | "
                    f"Peak ${pos['peak_price']:.6f} | "
                    f"Current ${current_price:.6f} | "
                    f"Stop ${trailing_stop_price:.6f}"
                )
                full_sells.append((token_mint, current_price, "TRAILING_STOP"))
                continue

            # --- 4. Time-Based Exit (full exit) ---
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
                full_sells.append((token_mint, current_price, "TIME_EXIT"))

        for token_mint, price, fraction, reason in partial_sells:
            self._sellPartialPosition(token_mint, price, fraction, reason)

        for token_mint, price, reason in full_sells:
            self._sellPosition(token_mint, price, reason)


    """
    Method Name:
        _sellPartialPosition

    Parameters:
        token_mint (str):
            Mint address of the token to partially sell.
        price (float):
            Current market price to sell at.
        fraction (float):
            Fraction of the current token balance to sell (e.g. 0.50 = 50%).
        reason (str):
            Label for why the partial sell was triggered (e.g. 'TAKE_PROFIT').

    Return:
        None

    Method Description:
        Executes a partial exit of an open position.

        - Sells `fraction` of the current token amount at 2% sell slippage.
        - Credits proceeds to balance.
        - Reduces the position's amount and cost_basis proportionally.
        - Sets tp_sold = True so this path cannot fire again for this position.
        - Persists the updated position and account balance.
        - Logs the partial trade to paper_trades (no trader performance update
          because the position is still open).
    """
    def _sellPartialPosition(self, token_mint: str, price: float, fraction: float, reason: str):
        if token_mint not in self.positions:
            return

        pos             = self.positions[token_mint]
        sell_amount     = pos["amount"] * fraction
        token_symbol    = pos["token_symbol"]
        wallet_address  = pos["wallet_address"]

        slipped_price   = price * 0.98
        proceeds        = sell_amount * slipped_price
        partial_cost    = pos["cost_basis"] * fraction
        realised_pnl    = proceeds - partial_cost

        self.balance       += proceeds
        pos["amount"]      -= sell_amount
        pos["cost_basis"]  -= partial_cost
        pos["tp_sold"]      = True

        now = datetime.now(timezone.utc)
        self.tradeHistory.append(
            Trade(token_symbol, 'SELL', slipped_price, sell_amount, now)
        )

        # Persist updated position and account balance
        self._save_position(token_mint)
        self._save_account()
        self._log_trade(
            wallet_address=wallet_address,
            token_out_mint=token_mint,
            token_symbol=token_symbol,
            side='SELL',
            price=slipped_price,
            amount=sell_amount,
            usd_value=proceeds,
            sell_reason=reason,
            realised_pnl=realised_pnl,
        )

        print(
            f"--------------------------------------"
            f"\n[PARTIAL SELL] {token_symbol} |\n "
            f"Reason: {reason} |\n "
            f"Sold {fraction*100:.0f}% ({sell_amount:.4f} tokens) |\n "
            f"Price ${slipped_price:.6f} |\n "
            f"Proceeds ${proceeds:.2f} |\n "
            f"Partial PnL ${realised_pnl:+.2f} |\n "
            f"Remaining {pos['amount']:.4f} tokens | "
            f"Balance ${self.balance:.2f}\n"
            f"--------------------------------------"
        )

        send_discord_alert_sync(
            f"🟡 **PARTIAL SELL** `{token_symbol[:20]}`\n"
            f"Reason: **{reason}**\n"
            f"Sold {fraction*100:.0f}% @ ${slipped_price:.6f}\n"
            f"Partial PnL: **${realised_pnl:+.2f}**\n"
            f"Balance: ${self.balance:.2f}"
        )

        self._broadcast_updates({
            "symbol": token_symbol,
            "side": "SELL",
            "price": slipped_price,
            "amount": sell_amount,
            "usd_value": proceeds,
            "sell_reason": reason,
            "realised_pnl": realised_pnl,
            "timestamp": now.isoformat(),
            "wallet_address": wallet_address
        })

        # -----------------------------------------------------------------------
        # Trade counter — increment on every partial sell event as well
        # -----------------------------------------------------------------------
        self.trade_count += 1
        print(
            f"  [TRADE COUNT] {self.trade_count}/{SAMPLE_SIZE if CONFIG_TEST_MODE else '∞'} "
            f"{'(config test mode)' if CONFIG_TEST_MODE else ''}"
        )

        if CONFIG_TEST_MODE and self.trade_count >= SAMPLE_SIZE:
            self._rotate_config()




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
            f"--------------------------------------"
            f"\n[SELL] {token_symbol} |\n "
            f"Reason: {reason} |\n "
            f"Price ${slipped_price:.6f} |\n "
            f"Proceeds ${proceeds:.2f} |\n "
            f"Realised PnL ${realised_pnl:+.2f} |\n "
            f"Balance ${self.balance:.2f}\n"
            f"--------------------------------------"
        )

        send_discord_alert_sync(
            f"{'🔴' if realised_pnl < 0 else '🟢'} **SELL** `{token_symbol[:20]}`\n"
            f"Reason: **{reason}**\n"
            f"PnL: **${realised_pnl:+.2f}**\n"
            f"Proceeds: ${proceeds:.2f} @ ${slipped_price:.6f}\n"
            f"Balance: ${self.balance:.2f}"
        )

        self._broadcast_updates({
            "symbol": token_symbol,
            "side": "SELL",
            "price": slipped_price,
            "amount": amount,
            "usd_value": proceeds,
            "sell_reason": reason,
            "realised_pnl": realised_pnl,
            "timestamp": now.isoformat(),
            "wallet_address": wallet_address
        })

        # -----------------------------------------------------------------------
        # Trade counter — increment on every completed (full) sell
        # -----------------------------------------------------------------------
        self.trade_count += 1
        print(
            f"  [TRADE COUNT] {self.trade_count}/{SAMPLE_SIZE if CONFIG_TEST_MODE else '∞'} "
            f"{'(config test mode)' if CONFIG_TEST_MODE else ''}"
        )

        if CONFIG_TEST_MODE and self.trade_count >= SAMPLE_SIZE:
            self._rotate_config()



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
        mode_label = "CONFIG TEST MODE" if CONFIG_TEST_MODE else "LIVE MODE"
        print(f"\nPaper Trading Engine started [{mode_label}]. Polling every {POLL_INTERVAL_SECONDS}s.\n")
        if CONFIG_TEST_MODE:
            total = self._count_total_configs()
            tested = self._count_tested_configs()
            print(
                f"  Configs in DB: {total} | Already tested: {tested} | "
                f"Remaining: {total - tested} | "
                f"Sample size per config: {SAMPLE_SIZE} trades\n"
            )
        try:
            while True:
                if self.reload_requested:
                    print("[Engine] Reloading targets...")
                    self.targets = self._load_targets()
                    self._ensure_trader_performance_rows()
                    self.reload_requested = False

                print(f"[{datetime.now().strftime('%H:%M:%S')}] --- Poll ---")
                self._price_cache.clear()

                # Buy side — check for new whale swaps
                new_swaps = self._fetch_new_swaps()
                if new_swaps:
                    for swap in new_swaps:
                        print(
                            f"[NEW SWAP] ID={swap['id']} | "
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

                if CONFIG_TEST_MODE:
                    tested = self._count_tested_configs()
                    total  = self._count_total_configs()
                    print(
                        f"  [Config id={self._current_config_id} | "
                        f"{tested}/{total} done] "
                        f"risk={RISK_PER_TRADE} tp={TAKE_PROFIT_PCT} split={TAKE_PROFIT_SPLIT} "
                        f"ts={TRAILING_STOP_PCT} sl={STOP_LOSS_PCT} hold={MAX_HOLD_SECONDS}s | "
                        f"Trades: {self.trade_count}/{SAMPLE_SIZE} | "
                        f"Portfolio: ${portfolio_val:.2f} | "
                        f"Cash: ${self.balance:.2f} | "
                        f"PnL: ${pnl:+.2f} | "
                        f"Open: {len(self.positions)}\n"
                    )
                else:
                    print(
                        f"  Portfolio: ${portfolio_val:.2f} | "
                        f"Cash: ${self.balance:.2f} | "
                        f"PnL: ${pnl:+.2f} | "
                        f"Trades: {self.trade_count} | "
                        f"Open positions: {len(self.positions)}\n"
                    )

                time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:

            print("\nPaper Trading Engine shutting down...")
            if CONFIG_TEST_MODE:
                self._print_test_summary()
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
        _broadcast_updates

    Parameters:
        trade_event (dict):
            A dictionary containing details of the executed trade, used to
            broadcast updates to the FastAPI backend for real-time frontend display.

    Return:
        None

    Method Description:
        After executing a trade (buy or sell), this helper method is called to
        broadcast the following updates to the FastAPI backend via HTTP POST:

        1. The new trade event is sent to the live feed channel.
        2. The updated account balance and initial balance are sent to the summary channel.
        3. The updated list of open positions is sent to the positions channel.

        These broadcasts enable real-time updates on the frontend dashboard without
        requiring the frontend to poll for changes. Any exceptions during broadcasting
        are caught and logged, but do not interrupt the trading engine's operation.
    """
    def _broadcast_updates(self, trade_event: dict):
        """Helper to broadcast state changes to the FastAPI backend"""
        try:
            # Broadcast the new trade to live feed
            requests.post("http://api:8000/api/internal/broadcast/live_feed", json=trade_event, timeout=1)
            
            # Broadcast updated account balance
            requests.post("http://api:8000/api/internal/trigger/summary", timeout=1)
            
            # Broadcast updated open positions list
            pos_list = [{
                "id": p["token_out_mint"],
                "symbol": p["token_symbol"],
                "amount": p["amount"],
                "entry_price": p["entry_price"],
                "peak_price": p["peak_price"],
                "cost_basis": p["cost_basis"],
                "wallet_address": p["wallet_address"]
            } for p in self.positions.values()]

            requests.post("http://api:8000/api/internal/broadcast/positions", json={"positions": pos_list}, timeout=1)
            
        except Exception as e:
            print(f"Failed to broadcast WebSocket update: {e}")

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

def trigger_websocket(channel: str, data: dict):
    try:
        # Uses the docker-compose service name 'api'
        requests.post(f"http://api:8000/api/internal/broadcast/{channel}", json=data)
    except Exception as e:
        print(f"Failed to broadcast {channel}: {e}")            


"""
Method Name:
    start_engine_api

Parameters:
        account_instance (PaperAccount):
            The instance of the PaperAccount engine, passed in so the API can
            call methods to reset the engine or update config live.

Return:
    None

Method Description:
    This method starts a lightweight Flask web server inside the engine process,
    listening on port 8001. It exposes two POST endpoints:

    1. /command/reset:
        Accepts a JSON payload with an optional "new_balance" field.
        When called, it resets the engine's portfolio to the specified new balance
        (or $10,000 if not provided) and clears all positions and trade history.

    2. /command/update_config:
        Accepts a JSON payload with any of the engine configuration parameters
        (risk_per_trade, take_profit_pct, take_profit_split, trailing_stop_pct,
            stop_loss_pct, max_hold_seconds).
        When called, it updates the engine's global configuration variables in real-time,
        allowing for dynamic tuning without restarting the engine.
"""
def start_engine_api(account_instance):
    """
    Starts a lightweight FastAPI server inside the engine to receive 
    live updates and reset commands from the main backend API.
    """
    app = FastAPI()

    # Define expected request models
    class ResetData(BaseModel):
        new_balance: float = 10000.0

    class ConfigData(BaseModel):
        risk_per_trade: float = None
        take_profit_pct: float = None
        take_profit_split: float = None
        trailing_stop_pct: float = None
        stop_loss_pct: float = None
        max_hold_seconds: int = None

    @app.post('/command/reset')
    def reset_engine(data: ResetData):
        account_instance.reset_portfolio(newBalance=data.new_balance)
        return {"status": "success", "message": f"Engine reset to ${data.new_balance}"}

    @app.post('/command/update_config')
    def update_config(data: ConfigData):
        global RISK_PER_TRADE, TAKE_PROFIT_PCT, TAKE_PROFIT_SPLIT
        global TRAILING_STOP_PCT, STOP_LOSS_PCT, MAX_HOLD_SECONDS
        
        if data.risk_per_trade is not None: RISK_PER_TRADE = data.risk_per_trade
        if data.take_profit_pct is not None: TAKE_PROFIT_PCT = data.take_profit_pct
        if data.take_profit_split is not None: TAKE_PROFIT_SPLIT = data.take_profit_split
        if data.trailing_stop_pct is not None: TRAILING_STOP_PCT = data.trailing_stop_pct
        if data.stop_loss_pct is not None: STOP_LOSS_PCT = data.stop_loss_pct
        if data.max_hold_seconds is not None: MAX_HOLD_SECONDS = data.max_hold_seconds
        
        # SET A FLAG instead of doing database operations in this thread
        account_instance.reload_requested = True
        
        return {"status": "success", "message": "Configuration updated live"}

    # Run the uvicorn server programmatically
    # log_level="warning" keeps the engine console clean from standard API logs
    uvicorn.run(app, host='0.0.0.0', port=8001, log_level="warning")

if __name__ == "__main__":
    # reset=False — persisted balance, positions and swap cursor are restored
    # on restart.  Pass reset=True only when you deliberately want a clean slate.
    account = PaperAccount(initialBalance=10000.0, reset=False, generate_config=False)

    # Start the FastAPI server in a separate thread so it doesn't block the main trading loop
    cmd_thread = threading.Thread(target=start_engine_api, args=(account,), daemon=True)
    cmd_thread.start()

    try:
        account.run()
    except KeyboardInterrupt:
        print("\nStopping engine...")