"""Чтение блокчейна Ethereum.

BlockchainGateway — интерфейс: что нам нужно от блокчейна (только чтение!).
EthereumRpcGateway — реализация через JSON-RPC любой ноды Ethereum.
В тестах вместо неё подставляется FakeBlockchain (tests/fakes.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ChainTransaction:
    hash: str
    from_address: str
    to_address: str | None
    value_wei: int
    chain_id: int | None
    block_number: int | None  # None — транзакция ещё в мемпуле


@dataclass(frozen=True)
class ChainReceipt:
    success: bool      # False — транзакция отклонена сетью (reverted)
    block_number: int


class BlockchainError(Exception):
    """Нода недоступна или вернула ошибку."""


class BlockchainGateway(ABC):
    """Интерфейс без методов отправки денег: сервис ничего не подписывает (non-custodial)."""

    @abstractmethod
    def get_transaction(self, tx_hash: str) -> ChainTransaction | None: ...

    @abstractmethod
    def get_receipt(self, tx_hash: str) -> ChainReceipt | None: ...

    @abstractmethod
    def get_block_number(self) -> int: ...


def _hex(value: str | None) -> int | None:
    return int(value, 16) if value else None


class EthereumRpcGateway(BlockchainGateway):
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self.http = httpx.Client(timeout=10)

    def call(self, method: str, params: list) -> object:
        """Один JSON-RPC запрос к ноде, например eth_blockNumber."""
        try:
            response = self.http.post(self.rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BlockchainError(f"RPC {method} не выполнен: {exc}") from exc
        if "error" in body:
            raise BlockchainError(f"RPC {method} вернул ошибку: {body['error']}")
        return body.get("result")

    def get_transaction(self, tx_hash: str) -> ChainTransaction | None:
        tx = self.call("eth_getTransactionByHash", [tx_hash])
        if tx is None:
            return None
        return ChainTransaction(
            hash=tx["hash"].lower(),
            from_address=tx["from"].lower(),
            to_address=tx["to"].lower() if tx.get("to") else None,
            value_wei=int(tx["value"], 16),
            chain_id=_hex(tx.get("chainId")),
            block_number=_hex(tx.get("blockNumber")),
        )

    def get_receipt(self, tx_hash: str) -> ChainReceipt | None:
        receipt = self.call("eth_getTransactionReceipt", [tx_hash])
        if not receipt or receipt.get("blockNumber") is None:
            return None  # ещё не попала в блок
        return ChainReceipt(success=receipt.get("status") == "0x1", block_number=int(receipt["blockNumber"], 16))

    def get_block_number(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)
