import os
import time

import requests

_BASE = "https://api.etherscan.io/v2/api"
_CHAIN_ID = 56  # BSC
_TIMEOUT = 10


class Transfer:
    __slots__ = ("from_addr", "to_addr", "value_tokens", "timestamp")

    def __init__(self, from_addr: str, to_addr: str, value_tokens: float, timestamp: int) -> None:
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.value_tokens = value_tokens
        self.timestamp = timestamp


def fetch_token_transfers(contract_addr: str, hours: int = 6) -> list[Transfer]:
    api_key = os.environ.get("BSCSCAN_API_KEY", "")
    if not api_key:
        return []

    try:
        resp = requests.get(
            _BASE,
            params={
                "chainid": _CHAIN_ID,
                "module": "account",
                "action": "tokentx",
                "contractaddress": contract_addr,
                "sort": "desc",
                "page": 1,
                "offset": 500,
                "apikey": api_key,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return []

    if data.get("status") != "1" or not isinstance(data.get("result"), list):
        return []

    cutoff = int(time.time()) - hours * 3600
    transfers: list[Transfer] = []

    for tx in data["result"]:
        ts = int(tx.get("timeStamp", 0))
        if ts < cutoff:
            break  # results are sorted desc, no need to continue
        decimals = int(tx.get("tokenDecimal") or 18)
        value = int(tx.get("value") or 0) / (10 ** decimals)
        transfers.append(Transfer(
            from_addr=tx.get("from", "").lower(),
            to_addr=tx.get("to", "").lower(),
            value_tokens=value,
            timestamp=ts,
        ))

    return transfers
