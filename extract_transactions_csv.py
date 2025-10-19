#import pandas as pd
import io
import os
import sys
import re
from src.transactions_extractor import Transaction

# IMPORTANT: This script is now designed to run from the command line.
# It expects the CSV file path as the first command-line argument.

def extract_financial_data(file_content: str) -> str:
    """
    Reads the IBKR Activity Statement CSV content, identifies the transactional
    data section, and extracts 'Dividend' and 'Tax' related transactions using 
    robust filtering based on common IBKR column headers.
    """
    try:
        # 1. Read the content line by line to find the starting point of the transaction table
        lines = file_content.strip().split('\n')

        start_line_index = -1
        
        # --- PRIMARY HEURISTIC (Most Robust for IBKR CSVs) ---
        # Search for the line that contains the actual column names used for trades/cash.
        # This line usually contains 'Header,' but the actual column names are on the line AFTER that header.
        # We need to find the line that contains both 'Description' and an 'Amount' or 'Proceeds' column.
        
        # We iterate to find the line containing the primary transaction column headers
        for i, line in enumerate(lines):
            # Look for common column names in the line, indicating the start of a transaction block
            if 'Description' in line and ('Amount' in line or 'Proceeds' in line) and 'Date' in line:
                
                # Check if this line is a 'Header' line itself, typically IBKR headers are unique per section
                # If it's the column name line, we set the start index to it.
                start_line_index = i
                break
        
        # --- SECONDARY HEURISTIC (Fallback: Look for section header and advance one line) ---
        # If the primary heuristic fails, look for the section title and assume the column names follow
        if start_line_index == -1:
             for i, line in enumerate(lines):
                # We look for a line starting with a known report title followed by the 'Header' marker
                if line.startswith(("Cash Report,", "Trades,", "Deposits & Withdrawals,", "Statement of Funds,")) and "Header," in line:
                    # The actual column headers are often on the NEXT line, so we set the start index to i + 1
                    # Note: We prioritize the search above, but if we land here, we take i+1
                    start_line_index = i + 1
                    break
            
        if start_line_index == -1:
            return "Error: Could not reliably find the transaction header row (line containing 'Description' and 'Date') in the CSV file."

        # The transactional data block starts at start_line_index.
        csv_data = "\n".join(lines[start_line_index:])

        # 2. Load the data into a pandas DataFrame
        # The 'python' engine and explicit separators/quotes are necessary for the IBKR format.
        df = pd.read_csv(
            io.StringIO(csv_data), 
            header=0,               # The first line of csv_data is now the correct column header row
            skipinitialspace=True,
            sep=',',
            quotechar='"',
            engine='python'         # Use the Python engine for better parsing of irregular lines
        )
        
        # Clean up column names (strip whitespace)
        df.columns = df.columns.str.strip()
        
        # 3. Data Cleaning: Drop rows where 'Description' is missing or non-transactional (e.g., 'Data' rows)
        if 'Description' not in df.columns:
             return f"Error: Could not find the 'Description' column in the transaction data. Found columns: {list(df.columns)}"

        # Drop any row that is missing a value in the Description column
        df.dropna(subset=['Description'], inplace=True)
        
        # Drop rows that are likely section headers or footers and not transactional data
        # We remove rows where the description is missing or is purely a report type marker.
        df = df[~df['Description'].str.contains('Summary|Header|Total|Net', case=False, na=False)]


        # 4. Filter for rows that are dividends or withholding tax
        keywords = ['Dividend', 'Tax', 'Withholding']
        
        # Create a boolean mask: True if any keyword is present in the 'Description' column (case-insensitive)
        mask = df['Description'].str.contains('|'.join(keywords), case=False, na=False)
        
        extracted_df = df[mask].copy()
        
        if extracted_df.empty:
            return "No Dividend or Tax transactions found in the statement."
            
        # 5. Select the most relevant columns for output
        
        # Identify the column containing the transactional amount (usually 'Proceeds' in Cash Report or 'Amount' elsewhere)
        amount_col = None
        
        # Find the column that contains the transactional amount using a prioritized list
        amount_cols_candidates = ['Proceeds', 'Amount', 'Value', 'Money']
        for candidate in amount_cols_candidates:
            # Look for exact match or column containing the candidate word, excluding 'Prior' (which is summary data)
            match = next((col for col in extracted_df.columns if candidate == col or (candidate in col and 'Prior' not in col)), None)
            if match:
                amount_col = match
                break

        
        # Define columns for display and their desired output names
        display_cols_map = {
            'Date': 'Date',
            'Currency': 'Currency',
            'Description': 'Transaction Type',
            'Symbol': 'Symbol',
        }
        
        # Add the identified amount column
        if amount_col:
            display_cols_map[amount_col] = 'Amount'
        else:
            return f"Error: The transactional amount column ('Proceeds' or 'Amount') could not be identified. Available columns: {list(extracted_df.columns)}"
        
        
        # Filter the DataFrame to only include available columns
        final_cols = [col for col in display_cols_map if col in extracted_df.columns]
        final_df = extracted_df[final_cols].copy()
        
        # Rename columns for cleaner output
        final_df.rename(columns={k: v for k, v in display_cols_map.items() if k in final_cols}, inplace=True)
        
        # Convert the amount column to numeric and handle missing symbols
        final_df['Amount'] = final_df['Amount'].astype(str).str.replace('"', '').str.strip()
        final_df['Amount'] = pd.to_numeric(final_df['Amount'], errors='coerce')
        final_df.dropna(subset=['Amount'], inplace=True)
        final_df['Symbol'] = final_df['Symbol'].fillna('N/A')
        
        if final_df.empty:
             return "All filtered rows had non-numeric values in the amount column, indicating an issue with column detection, or no relevant transactions were found."
             
        # 6. Format the output
        output = io.StringIO()
        output.write("--- Extracted Dividend and Tax Transactions (IBKR Statement) ---\n\n")
        
        # Print the data as a clean Markdown table
        output.write(final_df.to_markdown(index=False, floatfmt=".2f"))
        output.write("\n\n--------------------------------------------\n")
        output.write(f"Total {len(final_df)} relevant transactions extracted.")
        output.write("\n\n*Note: The 'Amount' column represents the value of the transaction. Dividends are typically positive, and Taxes/Withholding are negative.*")

        return output.getvalue()

    except Exception as e:
        return f"An unexpected error occurred during processing the CSV data. Please check the file format. Error: {e}"

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

# --- Original Execution Block (Deactivated for Command Line Use) ---
# This block is for in-platform execution only and is commented out for external use.
# if 'file_manager' in locals() or 'file_manager' in globals():
#     try:
#         # file_manager.read_file() provides the full content of the uploaded CSV
#         FILE_ID = "uploaded:U10968540_20250901_20251017.csv"
#         file_content = file_manager.read_file(FILE_ID)
#         if file_content:
#             result = extract_financial_data(file_content)
#             print(result)
#         else:
#             print(f"Error: Could not read content for file ID {FILE_ID}.")
#     except Exception as e:
#         print(f"File Manager Error: {e}")
# else:
#     # We keep this message for the in-platform console output if not run via command line
#     pass
