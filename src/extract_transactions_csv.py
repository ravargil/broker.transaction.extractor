#import pandas as pd
import io
import os
import sys
import re
from src.transactions_extractor import Transaction

# IMPORTANT: This script is now designed to run from the command line.
# It expects the CSV file path as the first command-line argument.

def extract_symbol_and_dividend_per_share(description: str):
    """
    Extracts the symbol (all letters until '(') and dividend per share (float) from the description field.
    Example: "HSY(US4278661081) Cash Dividend USD 1.37 per Share (Ordinary Dividend)"
    Returns: (symbol: str, dividend_per_share: float)
    """
    # Extract symbol: all letters before '('
    symbol_match = re.match(r'^([A-Z]+)\(', description)
    symbol = symbol_match.group(1) if symbol_match else None

    # Extract dividend per share: look for 'USD <number> per Share'
    dividend_match = re.search(r'USD\s*([\d.]+)\s*per Share', description)
    dividend_per_share = float(dividend_match.group(1)) if dividend_match else None

    return symbol, dividend_per_share

def convert_dividend_line_to_transaction(line: str):
    # Assuming the line is a CSV string, we split it and extract relevant fields
    fields = line.split(',')
    date = fields[3]  # Example index for date
    symbol, dividend_per_share = extract_symbol_and_dividend_per_share(fields[4])  # Example index for description
    amount = float(fields[5])  # Example index for amount

    return Transaction(
        date=date,
        transaction_type='Dividend', # TODO: take from pre-defined configuration
        symbol=symbol,
        amount=amount,
        Broker='Interactive Brokers', # TODO : take from pre-defined configuration
        DividendPerShare=dividend_per_share,
    )

def extract_dividend_data(file_content: str) -> str:
    # Iterate over lines in file_content and extract those starting with "Dividends,Header,"
    dividends_header_lines = [line for line in file_content.splitlines() if line.startswith("Dividends,Header,")]
    if len(dividends_header_lines) > 1:
        raise Exception("Multiple 'Dividends,Header,' lines found in the file.")
    print(dividends_header_lines)

    dividends_lines = [line for line in file_content.splitlines() if line.startswith("Dividends,Data,")]
    print(dividends_lines)
    dividend_transactions = []
    for line in dividends_lines:
        transaction = convert_dividend_line_to_transaction(line)
        dividend_transactions.append(transaction)
    return dividend_transactions

def extract_buy_data(file_content: str) -> list:
    """
    Extracts all 'buy' transactions from the IBKR CSV file content.
    Returns a list of Transaction objects for each buy order.
    """
    buy_transactions = []
    # Find all lines that represent a trade order in stocks (buys and sells)
    trade_lines = [line for line in file_content.splitlines() if line.startswith("Trades,Data,Order,Stocks,")]
    for line in trade_lines:
        fields = line.split(',')
        # Defensive: Ensure enough fields
        if len(fields) < 10:
            continue
        # Quantity: positive for buy, negative for sell
        try:
            quantity = float(fields[8])
        except ValueError:
            continue
        if quantity > 0:
            # Extract relevant fields
            date = fields[6].strip('"')
            symbol = fields[5]
            try:
                amount = float(fields[9]) # For buy transactions, amount is the trading price
            except ValueError:
                amount = None
            transaction = Transaction(
                date=date,
                transaction_type='Buy',
                symbol=symbol,
                quantity=quantity,
                amount=amount,
                Broker='Interactive Brokers'
            )
            buy_transactions.append(transaction)
    return buy_transactions

def extract_deposit_data(file_content: str) -> list:
    """
    Extracts all deposit transactions from the IBKR CSV file content.
    Returns a list of Transaction objects for each deposit.
    """
    deposit_transactions = []
    # Find all lines that represent deposits
    deposit_lines = [line for line in file_content.splitlines() if line.startswith("Deposits & Withdrawals,Data,")]
    for line in deposit_lines:
        fields = line.split(',')
        # Defensive: Ensure enough fields
        if len(fields) < 5:
            raise ValueError("Insufficient fields in deposit transaction line.")
        if fields[2].startswith("Total"):
            continue  # Skip summary lines
        if fields[2] != "ILS":
            raise ValueError("Unsupported currency for deposit transaction. Only ILS is supported.")
        if fields[4] != "Electronic Fund Transfer":
            raise ValueError("Unsupported deposit type. Only 'Electronic Fund Transfer' is supported.")
        # Extract relevant fields
        date = fields[3].strip('"')
        try:
            amount = float(fields[5])
        except ValueError:
            amount = None
        transaction = Transaction(
            date=date,
            transaction_type='Cash Transfer',
            symbol='',
            amount=amount,
            Broker='Interactive Brokers'
        )
        deposit_transactions.append(transaction)
    return deposit_transactions
# --- Command Line Execution Block ---
# This block runs the script when executed directly from the command line.
if __name__ == '__main__':
    # Check if a file path argument was provided
    if len(sys.argv) < 2:
        print("Usage: python extract_transactions.py <path/to/your/ibkr_statement.csv>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    
    if not os.path.exists(file_path):
        print(f"Error: The file '{file_path}' was not found.")
        sys.exit(1)
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
            
        transactions = extract_dividend_data(file_content)
        print(transactions)
        print("\n---\n")

        transactions = extract_buy_data(file_content)
        print(transactions)
        print("\n---\n")

        transactions = extract_deposit_data(file_content)
        print(transactions)
        print("\n---\n")

    except Exception as e:
        print(f"A critical error occurred while reading or processing the file: {e}")
        sys.exit(1)
