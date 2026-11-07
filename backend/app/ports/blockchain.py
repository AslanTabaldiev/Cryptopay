"""Port: read-only access to a blockchain.

The gateway is non-custodial, so this interface deliberately has no methods
for signing or sending transactions (Interface Segregation).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ChainTransaction:
    hash: str
    from_address: str
    to_address: str | None
    value_wei: int
    chain_id: int | None
    block_number: int | None  # None while the tx is still in the mempool


@dataclass(frozen=True)
class ChainReceipt:
    success: bool
    block_number: int


class BlockchainError(Exception):
    """The blockchain node could not be reached or returned an error."""


class BlockchainGateway(ABC):
    @abstractmethod
    def get_transaction(self, tx_hash: str) -> ChainTransaction | None:
        """Return the transaction, or None if the node does not know it (yet)."""

    @abstractmethod
    def get_receipt(self, tx_hash: str) -> ChainReceipt | None:
        """Return the receipt, or None if the transaction is not mined yet."""

    @abstractmethod
    def get_block_number(self) -> int:
        """Return the number of the latest block."""
