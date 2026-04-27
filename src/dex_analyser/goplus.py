import requests

from .models import TokenSafety

_BASE = "https://api.gopluslabs.io/api/v1"
_TIMEOUT = 8

_EVM_CHAINS: dict[str, str] = {
    "ethereum": "1",
    "bsc": "56",
    "polygon": "137",
    "arbitrum": "42161",
    "avalanche": "43114",
    "optimism": "10",
    "base": "8453",
    "cronos": "25",
    "fantom": "250",
    "zksync": "324",
    "linea": "59144",
}


def _lp_locked_pct(info: dict) -> float:
    lp_total = float(info.get("lp_total_supply") or 0)
    if lp_total <= 0:
        return 0.0
    locked = sum(
        float(h.get("balance", 0))
        for h in (info.get("lp_holders") or [])
        if h.get("is_locked") == 1 or h.get("tag") in ("Burn", "burn")
    )
    return min(locked / lp_total * 100, 100.0)


def _parse_evm(info: dict) -> TokenSafety:
    owner = info.get("owner_address") or ""
    renounced = not owner.strip().strip("0x").strip("0")
    return TokenSafety(
        is_honeypot=info.get("is_honeypot") == "1",
        buy_tax=float(info.get("buy_tax") or 0),
        sell_tax=float(info.get("sell_tax") or 0),
        is_mintable=info.get("is_mintable") == "1",
        owner_renounced=renounced,
        lp_locked_pct=_lp_locked_pct(info),
        is_blacklist=info.get("is_blacklisted") == "1",
    )


def _parse_solana(info: dict) -> TokenSafety:
    return TokenSafety(
        is_honeypot=False,
        buy_tax=0.0,
        sell_tax=float(info.get("transfer_fee_rate") or 0) * 100,
        is_mintable=bool(info.get("mint_authority")),
        owner_renounced=not bool(info.get("mint_authority")),
        lp_locked_pct=0.0,
        is_blacklist=bool(info.get("freeze_authority")),
    )


def fetch_safety(chain: str, address: str) -> TokenSafety | None:
    chain_lower = chain.lower()
    try:
        if chain_lower == "solana":
            resp = requests.get(
                f"{_BASE}/solana/token_security",
                params={"contract_addresses": address},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 1:
                return None
            result = data.get("result") or {}
            info = result.get(address) or result.get(address.lower()) or {}
            return _parse_solana(info) if info else None

        if chain_lower in _EVM_CHAINS:
            resp = requests.get(
                f"{_BASE}/token_security/{_EVM_CHAINS[chain_lower]}",
                params={"contract_addresses": address.lower()},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 1:
                return None
            result = data.get("result") or {}
            info = result.get(address.lower()) or result.get(address) or {}
            return _parse_evm(info) if info else None

    except requests.RequestException:
        pass

    return None
