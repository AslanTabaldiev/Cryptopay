"""Adapter: BlockchainGateway implemented over Ethereum JSON-RPC (any EVM node)."""

from __future__ import annotations

import itertools
from typing import Any

import httpx

from app.ports.blockchain import BlockchainError, BlockchainGateway, ChainReceipt, ChainTransaction


def _hex_to_int(value: str | None) -> int | None:
    return int(value, 16) if value else None


class EthereumJsonRpcGateway(BlockchainGateway):
    def __init__(self, rpc_url: str, timeout: float = 10.0, client: httpx.Client | None = None):
        self._rpc_url = rpc_url
        self._http = client or httpx.Client(timeout=timeout)
        self._ids = itertools.count(1)

    def _call(self, method: str, params: list[Any]) -> Any:
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}
        try:
            response = self._http.post(self._rpc_url, json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BlockchainError(f"RPC request {method} failed: {exc}") from exc
        if "error" in body:
            raise BlockchainError(f"RPC error in {method}: {body['error']}")
        return body.get("result")

    def get_transaction(self, tx_hash: str) -> ChainTransaction | None:
        tx = self._call("eth_getTransactionByHash", [tx_hash])
        if tx is None:
            return None
        return ChainTransaction(
            hash=tx["hash"].lower(),
            from_address=tx["from"].lower(),
            to_address=tx["to"].lower() if tx.get("to") else None,
            value_wei=int(tx["value"], 16),
            chain_id=_hex_to_int(tx.get("chainId")),
            block_number=_hex_to_int(tx.get("blockNumber")),
        )

    def get_receipt(self, tx_hash: str) -> ChainReceipt | None:
        receipt = self._call("eth_getTransactionReceipt", [tx_hash])
        if receipt is None or receipt.get("blockNumber") is None:
            return None
        return ChainReceipt(
            success=receipt.get("status") == "0x1",
            block_number=int(receipt["blockNumber"], 16),
        )

    def get_block_number(self) -> int:
        return int(self._call("eth_blockNumber", []), 16)
