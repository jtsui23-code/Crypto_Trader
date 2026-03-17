import time
from typing import Dict, List
from datetime import datetime


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
    simplified slippage assumptions.

Member Variables:
    balance (float):
        Current available USD balance.
    positions (Dict[str, float]):
        Mapping of token symbol to amount currently held.
    tradeHistory (List[Trade]):
        List of all executed trades.
    initialBalance (float):
        Starting account balance used for PnL calculation.
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
        balance, empty positions dictionary, and empty trade history.
    """
    def __init__(self, initialBalance: float = 10000.0):
        self.balance = initialBalance
        self.initialBalance = initialBalance
        self.positions: Dict[str, float] = {}
        self.tradeHistory: List[Trade] = []


    """
    Method Name:
        executeCopy

    Parameters:
        token (str):
            Asset symbol being copied.
        price (float):
            Observed market price.
        amountUSD (float):
            USD amount to allocate for the trade.

    Return:
        bool:
            True if trade executed successfully.
            False if insufficient funds.

    Method Description:
        Simulates a copy-trade execution.

        - Verifies sufficient account balance.
        - Applies assumed slippage (2% worse price for buys).
        - Calculates token quantity purchased.
        - Updates account balance and positions.
        - Records trade in trade history.
    """
    def executeCopy(self, token: str, price: float, amountUSD: float) -> bool:
        if amountUSD > self.balance:
            print(f"Insufficient funds to copy trade {token}")
            return False

        # Apply 2% slippage for buy orders
        effective_price = price * 1.02

        tokens_bought = amountUSD / effective_price
        self.balance -= amountUSD
        self.positions[token] = self.positions.get(token, 0) + tokens_bought

        self.tradeHistory.append(
            Trade(token, 'BUY', effective_price, tokens_bought, datetime.now())
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
        total_value = 0

        for token, amount in self.positions.items():
            price = currentPrices.get(token, 0)
            total_value += (amount * price)

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
    

mock_prices = {
    "SOL": 150.00,
    "BONK": 0.02,
    "JUP": 1.10,
    "Dogwithhat": 2.30,
    "Render": 6.15,
    "Popcat": 0.98
}

if __name__ == "__main__":
    import random

    # Initialize the account with $10,000
    my_account = PaperAccount(initialBalance=10000.0)
    print(f"Account Initialized. Balance: ${my_account.getBalance():.2f}")
    test_buy_amount = 100.0

    try:
        while True:
            # Execute a simulated trade automatically
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] --- Trade Triggered ---")
            
            token, price = random.choice(list(mock_prices.items()))
            

            # Mocking a trade: Buying $500 worth of token at a mock price
            success = my_account.executeCopy(token=token, price=price, amountUSD=test_buy_amount)
            
            if success:
                print(f"Successfully bought ${test_buy_amount} of {token} at ${price} per token with 2% slippage. New Balance: ${my_account.getBalance():.2f}")
            else:
                print("Trade failed, insufficient funds.")

            # Update and display portfolio status
            market_prices = {"SOL": 150.00} # Mock current market price
            portfolio_val = my_account.getPortfolioValue(mock_prices)
            
            print(f"Status Update - Portfolio Value: ${portfolio_val:.2f} | "
                  f"Cash: ${my_account.getBalance():.2f}")
            
            # Wait for 30 seconds before the next trade
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\nPaper Trader shutting down...")