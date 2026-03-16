import os
import psycopg2
from solana.rpc.api import Client
from solders.signature import Signature
from dotenv import load_dotenv
from trader.scripts.get_whales import get_whales


"""
Class Name:
    Decoder

Description:
    The Decoder class is responsible for connecting to the Solana blockchain, 
    fetching transaction data, decoding token and SOL balance changes, 
    and saving relevant swap information to a PostgreSQL database. 
    It serves as the core component for processing whale transactions and 
    extracting actionable insights for the trading engine.

Member Variables:
    database_url (str):
        The URL of the PostgreSQL database.
    rpc_url (str):
        The URL of the Solana RPC endpoint.
    client (Client):
        The Solana RPC client.
"""
class Decoder:
    
    """
    Method Name:
        __init__

    Parameters:
        rpc_url (str):
            WebSocket RPC endpoint URL.
            Defaults to Solana mainnet-beta public endpoint.

    Return:
        None

    Method Description:
        Initializes the Decoder by setting the RPC URL, loading environment variables, 
        and establishing a connection to the Solana RPC client.
    """
    def __init__(self, rpc_url="https://api.mainnet-beta.solana.com"):
        load_dotenv()
        self.database_url = os.getenv("DATABASE_URL")
        self.rpc_url = rpc_url
        self.client = Client(self.rpc_url)

    """
    Method Name:
        _save_to_db

    Parameters:
        owner (str):
            The wallet address of the whale involved in the swap.
        token_out_mint (str):
            The mint address of the token being sold.
        amount_out (float):
            The quantity of the token being sold.
        token_in_mint (str):
            The mint address of the token being bought.
        amount_in (float):
            The quantity of the token being bought.
        price_per_token (float):
            The calculated price per token for the swap.

    Return:
        None


    Method Description:
        Saves decoded swap data to the PostgreSQL database. 
        It creates the swaps table if it doesn't exist and 
        then inserts a new record for each decoded swap transaction.
    """
    def _save_to_db(self, owner: str, token_out_mint: str, amount_out: float, token_in_mint: str, amount_in: float, price_per_token: float):
        '''Saves decoded swap data to the PostgreSQL database.'''
        try:
            conn = psycopg2.connect(self.database_url)
            cur = conn.cursor()
            
            '''
            Create the swaps table if it doesn't exist. 
            This ensures that the database is ready to store swap data without requiring a separate setup step. 
            The table includes columns for the owner, token mints, amounts, price per token, and a timestamp for when the swap was recorded.
            '''
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
            
            '''Insert the swap data into the database.'''
            cur.execute(
                """INSERT INTO swaps (owner, token_out_mint, amount_out, token_in_mint, amount_in, price_per_token) 
                VALUES (%s, %s, %s, %s, %s, %s)""",
                (owner, token_out_mint, amount_out, token_in_mint, amount_in, price_per_token)
            )
            
            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            print(f"Database error: {e}")


    """
    Method Name:
        _fetch_transaction

    Parameters:
        signature (str):
            The transaction signature to fetch from the Solana blockchain.

    Return:
        Transaction:
            The fetched transaction object or an error if the transaction is not found.

    Method Description:
        Fetches a transaction from the Solana blockchain using the provided signature. 
        It uses the Solana RPC client to retrieve the transaction details,
        which are then used for decoding token and SOL changes.
    """
    def _fetch_transaction(self, signature: str):
        ''''Fetches a transaction from the Solana blockchain using the provided signature.'''
        tx = self.client.get_transaction(
            Signature.from_string(signature),
            encoding="jsonParsed",
            max_supported_transaction_version=0
        )
        return tx.value


    """
    Method Name:
        _decode_token_changes

    Parameters:
        tx (Transaction):
            The transaction object containing token balance changes to decode.

    Return:
        List[Dict]:
            A list of dictionaries representing net token balance changes for each owner and mint.

    Method Description:
        Decodes token balance changes from a transaction by comparing pre and post balances. 
        It aggregates changes for each owner and mint to find the net change, 
        which is essential for accurately determining the tokens involved in a swap.
    """
    def _decode_token_changes(self, tx: str):
        '''Decodes token balance changes from a transaction, aggregating pre and post balances to find net changes per owner and mint.'''
        meta = tx.transaction.meta

        pre = meta.pre_token_balances
        post = meta.post_token_balances

        aggregated_changes = {}

        '''
        Iterate over post balances to find net changes for each owner and mint. 
        Then iterate over pre balances to calculate the difference. 
        This way we can handle cases where an account is both a sender and receiver in the same transaction.
        '''
        for p in post:
            owner = str(p.owner)
            mint = str(p.mint)
            post_amt = float(p.ui_token_amount.ui_amount or 0)

            pre_amt = 0
            for pre_token in pre:
                if str(pre_token.owner) == owner and str(pre_token.mint) == mint:
                    pre_amt = float(pre_token.ui_token_amount.ui_amount or 0)

            '''
            Calculate the difference between post and pre amounts. 
            If there is a change, store it in the aggregated_changes dictionary using a tuple of (owner, mint) as the key. 
            This allows us to easily sum changes for the same owner and mint across multiple entries in the pre and post lists.
            '''
            diff = post_amt - pre_amt
            if diff != 0:
                # Keys must be strings to be hashable and comparable
                key = (owner, mint)
                aggregated_changes[key] = diff

        '''Convert the aggregated changes dictionary into a list of dictionaries with owner, mint, and change keys for easier processing later on.'''
        return [
            {"owner": k[0], "mint": k[1], "change": v} 
            for k, v in aggregated_changes.items()
        ]

    """
    Method Name:
        _decode_sol_changes

    Parameters:
        tx (Transaction):
            The transaction object containing SOL balance changes to decode.

    Return:
        List[Dict]:
            A list of dictionaries representing net SOL balance changes for each owner.

    Method Description:
        Decodes SOL balance changes from a transaction by comparing pre and post balances. 
        It aggregates changes for each owner to find the net change, 
        which is essential for accurately determining the SOL involved in a swap.
    """
    def _decode_sol_changes(self, tx: str):
        '''Decodes SOL changes from a transaction, accounting for wrapped SOL as tokens.'''
        meta = tx.transaction.meta
        account_keys = tx.transaction.transaction.message.account_keys

        sol_changes = []

        '''Iterate over pre and post balances to find net SOL changes for each account. Filter out small changes that are likely just network fees.'''
        for i, (pre, post) in enumerate(zip(meta.pre_balances, meta.post_balances)):
            diff = (post - pre) / 1e9  # lamports to SOL
            if abs(diff) > 0.0001:  # filter small changes/network fees
                owner = str(account_keys[i].pubkey)
                sol_changes.append({"owner": owner, "mint": "So11111111111111111111111111111111111111112", "change": diff})
        
        return sol_changes

    """
    Method Name:
        decode_swap

    Parameters:
        signature (str):
            The transaction signature to decode for swap details.

    Return:
        None

    Method Description:
        Main function to decode a transaction and save relevant whale swap data to the database. 
        It fetches the transaction, decodes token and SOL changes, combines them while avoiding double-counting wrapped SOL, 
        filters for changes involving whale wallets, and then decodes the swap details to save to the database.
    """
    def decode_swap(self, signature: str):
        '''Main function to decode a transaction and save relevant whale swap data to the database.'''
        tx = self._fetch_transaction(signature)

        if not tx:
            print("Transaction not found")
            return

        '''Decode token changes and SOL changes, then combine them while avoiding double-counting wrapped SOL.'''
        token_changes = self._decode_token_changes(tx)
        sol_changes = self._decode_sol_changes(tx)
        all_changes = token_changes.copy()

        for sol in sol_changes:
            '''Check if this SOL change is already represented as a token change (wrapped SOL) to avoid double-counting.'''
            already_tracked = any(
                c['owner'] == sol['owner'] and c['mint'] == sol['mint'] 
                for c in token_changes
            )
            if not already_tracked:
                all_changes.append(sol)

        '''Fetch the list of whale wallets and filter changes to only those involving whales. Then decode the swap details and save to the database.'''
        whales = get_whales()
        unique_owners_in_tx = {c['owner'] for c in all_changes}

        '''Iterate over unique owners involved in the transaction and check if they are whales. If so, decode the swap details and save to the database.'''
        for owner in unique_owners_in_tx:
            if owner in whales:
                owner_changes = [c for c in all_changes if c['owner'] == owner]

                token_out = next((c for c in owner_changes if c['change'] < 0), None)
                token_in = next((c for c in owner_changes if c['change'] > 0), None)

                '''If we have both a token out and a token in for this owner, we can calculate the price per token and save the swap details to the database.'''
                if token_in and token_out:
                    owner = owner
                    price_per_token = abs(token_out['change']) / token_in['change']
                    token_out_change = abs(token_out['change'])
                    token_out_mint = token_out['mint']
                    token_in_change = abs(token_in['change'])
                    token_in_mint = token_in['mint']

                    self._save_to_db(str(owner), str(token_out_mint), token_out_change, str(token_in_mint), token_in_change, price_per_token)