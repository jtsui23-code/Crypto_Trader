import alpaca_trade_api as tradeapi
import os
from dotenv import load_dotenv

load_dotenv()

class PaperTradeEngine:
    def __init__(self):

        self.api = tradeapi.REST(
            os.getenv("ALPACA_API_KEY"),
            os.getenv("ALPACA_SECRET_KEY"),
            base_url="https://paper-api.alpaca.markets" # Paper environment 
        )

    def get_account_status(self): 
        """Checks current buying power and equity ."""
        account = self.api.get_account()
        return {
            "buying_power": account.buying_power,
            "equity": account.equity,
            "currency": account.currency
        }

    def execute_whale_copy(self, symbol, side, qty):
        """
        Executes a trade on Alpaca based on a whale's move [cite: 140-143].
        symbol: e.g., 'SOL/USD'
        side: 'buy' or 'sell'
        """
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type='market',
                time_in_force='gtc'
            )
            print(f"Alpaca {side} order submitted for {qty} {symbol}")
            return order
        except Exception as e:
            print(f"Alpaca Trade Error: {e}")
            return None