from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

@dataclass
class Transaction:
    """Data class for a single transaction."""
    date: str
    transaction_type: str
    symbol: str
    amount: float
    quantity: float = 0.0
    fees: float = 0.0
    cost: str = ""
    Broker: str = ""
    DividendPerShare: float = 0.0
    Comment: str = ""

class TransactionsExtractor(ABC):
    @abstractmethod
    def extract_transactions(self, file_path: str) -> List[Transaction]:
        """
        Extracts transactions from the given broker statement file.

        Args:
            file_path (str): Path to the broker statement file.

        Returns:
            List[Transaction]: List of extracted transactions.
        """
        pass