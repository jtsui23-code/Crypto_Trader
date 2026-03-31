"""
wallet_checker.py
-----------------
Checks each Solana wallet in data/whales.json using the public Solana RPC.
No API key required. No third-party services.

For each wallet it reports:
  - Whether the account exists on-chain
  - SOL balance
  - Number of recent transactions
  - Whether recent transactions involve known gambling programs
  - A verdict: OK / WARN / FLAGGED

Usage:
    python wallet_checker.py

Requirements:
    pip install requests
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WHALES_FILE = Path(__file__).parent / "check_wallet.json"

# Public Solana RPC endpoints (tried in order if one fails)
RPC_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com",
    "https://rpc.ankr.com/solana",
    "https://solana-mainnet.g.alchemy.com/v2/demo",
]

# Seconds to wait between wallet requests (avoid rate limiting)
REQUEST_DELAY = 1.2

# How many recent transactions to scan per wallet
TX_SCAN_LIMIT = 20

# Known gambling / high-risk program addresses on Solana
GAMBLING_PROGRAMS = {
    "RLBxxFkseAZ4RgJH3Sqn8jXxhmGoz9jWxDNJMh8pL7a": "Rollbit",
    "DCF4GZtNkBKCRHEg72r62TJ1CkUGpnbPxHMNkCmFQCZ": "DegenCoinFlip",
    "EHCBn4JmMKFMEVCsZCBicnNfNqRhrmQQmEWr5JB1kZNs": "Zeebit",
    "dp2waEWSBy5161fqs1s29KDtCLMgSGkPDRMi47e1YXv":  "DiceApp",
    "J4tSdMNsBYeB2KSSDY7o5HCqJ4wfNXFwBStLFWf2Bq3o": "Solana Casino",
}

# ---------------------------------------------------------------------------
# RPC helpers
# ---------------------------------------------------------------------------

_active_rpc = RPC_ENDPOINTS[0]

def rpc_call(method: str, params: list):
    global _active_rpc
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    headers = {"Content-Type": "application/json"}
    for endpoint in RPC_ENDPOINTS:
        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                _active_rpc = endpoint
                return resp.json()
        except Exception:
            continue
    return None


def get_balance(address: str):
    result = rpc_call("getBalance", [address])
    if result and "result" in result:
        lamports = result["result"].get("value", 0)
        return lamports / 1_000_000_000
    return None


def get_account_info(address: str):
    result = rpc_call("getAccountInfo", [address, {"encoding": "base58"}])
    if result and "result" in result:
        return result["result"].get("value")
    return None


def get_recent_transactions(address: str, limit: int = TX_SCAN_LIMIT) -> list:
    result = rpc_call("getSignaturesForAddress", [address, {"limit": limit}])
    if result and "result" in result:
        return result["result"] or []
    return []


def get_transaction(signature: str):
    result = rpc_call(
        "getTransaction",
        [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    )
    if result and "result" in result:
        return result["result"]
    return None


# ---------------------------------------------------------------------------
# Gambling detection
# ---------------------------------------------------------------------------

def check_gambling_in_tx(tx: dict) -> list:
    hits = []
    if not tx:
        return hits
    try:
        account_keys = (
            tx.get("transaction", {})
              .get("message", {})
              .get("accountKeys", [])
        )
        for key in account_keys:
            addr = key if isinstance(key, str) else key.get("pubkey", "")
            if addr in GAMBLING_PROGRAMS:
                site = GAMBLING_PROGRAMS[addr]
                if site not in hits:
                    hits.append(site)
    except Exception:
        pass
    return hits


# ---------------------------------------------------------------------------
# Per-wallet check
# ---------------------------------------------------------------------------

def check_wallet(address: str) -> dict:
    result = {
        "address": address,
        "exists": False,
        "sol_balance": None,
        "recent_tx_count": 0,
        "failed_txs": 0,
        "gambling_hits": [],
        "verdict": "UNKNOWN",
        "notes": [],
    }

    balance = get_balance(address)
    if balance is None:
        result["verdict"] = "UNKNOWN"
        result["notes"].append("RPC call failed — check your internet connection")
        return result

    result["exists"] = True
    result["sol_balance"] = balance

    if balance == 0.0:
        result["notes"].append("Zero SOL balance")

    acct = get_account_info(address)
    if acct is None and balance == 0.0:
        result["notes"].append("Account not found on-chain — may be closed")

    sigs = get_recent_transactions(address)
    result["recent_tx_count"] = len(sigs)

    if len(sigs) == 0:
        result["notes"].append("No transaction history found")

    failed = [s for s in sigs if s.get("err") is not None]
    result["failed_txs"] = len(failed)
    if len(failed) > 5:
        result["notes"].append(f"{len(failed)} of last {len(sigs)} txs failed")

    gambling_hits = []
    for sig_info in sigs[:10]:
        sig = sig_info.get("signature", "")
        if not sig:
            continue
        tx = get_transaction(sig)
        hits = check_gambling_in_tx(tx)
        for h in hits:
            if h not in gambling_hits:
                gambling_hits.append(h)
        time.sleep(0.2)

    result["gambling_hits"] = gambling_hits
    if gambling_hits:
        result["notes"].append(f"Gambling interactions: {', '.join(gambling_hits)}")

    if gambling_hits:
        result["verdict"] = "FLAGGED"
    elif balance == 0.0 and len(sigs) == 0:
        result["verdict"] = "WARN"
    elif result["notes"]:
        result["verdict"] = "WARN"
    else:
        result["verdict"] = "OK"

    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

ICONS = {"OK": "✅", "WARN": "⚠️ ", "FLAGGED": "🚨", "UNKNOWN": "❓"}

def print_result(r: dict):
    icon = ICONS.get(r["verdict"], "?")
    print(f"\n{icon} {r['address']}")
    print(f"   Verdict      : {r['verdict']}")
    if r["sol_balance"] is not None:
        print(f"   SOL Balance  : {r['sol_balance']:.4f}")
    print(f"   Recent Txs   : {r['recent_tx_count']}  (failed: {r['failed_txs']})")
    if r["gambling_hits"]:
        print(f"   Gambling     : {', '.join(r['gambling_hits'])}")
    for note in r["notes"]:
        print(f"   Note         : {note}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    wf = WHALES_FILE
    if not wf.exists():
        alt = Path(__file__).parent.parent / "data" / "whales.json"
        if alt.exists():
            wf = alt
        else:
            print(f"ERROR: whales.json not found at {wf} or {alt}")
            return

    with open(wf) as f:
        data = json.load(f)

    wallets = data["wallets"] if isinstance(data, dict) else data
    print(f"Checking {len(wallets)} wallets via Solana RPC...\n")
    print("=" * 60)

    results = []
    for i, address in enumerate(wallets, 1):
        print(f"[{i}/{len(wallets)}] {address[:8]}...", end="", flush=True)
        r = check_wallet(address)
        results.append(r)
        icon = ICONS.get(r["verdict"], "?")
        bal = f"  {r['sol_balance']:.3f} SOL" if r["sol_balance"] is not None else ""
        print(f" → {r['verdict']}{bal}")
        time.sleep(REQUEST_DELAY)

    print("\n" + "=" * 60)
    print("DETAILED RESULTS")
    print("=" * 60)
    for r in results:
        print_result(r)

    ok      = [r for r in results if r["verdict"] == "OK"]
    warn    = [r for r in results if r["verdict"] == "WARN"]
    flagged = [r for r in results if r["verdict"] == "FLAGGED"]
    unknown = [r for r in results if r["verdict"] == "UNKNOWN"]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  ✅ OK      : {len(ok)}")
    print(f"  ⚠️  WARN   : {len(warn)}")
    print(f"  🚨 FLAGGED : {len(flagged)}")
    print(f"  ❓ UNKNOWN : {len(unknown)}")

    if warn or flagged:
        print("\nWallets needing attention:")
        for r in warn + flagged:
            print(f"  {ICONS[r['verdict']]} {r['address']}")

    report_path = Path(__file__).parent / "wallet_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rpc_used": _active_rpc,
            "total": len(wallets),
            "summary": {"ok": len(ok), "warn": len(warn), "flagged": len(flagged), "unknown": len(unknown)},
            "results": results,
        }, f, indent=2, default=str)
    print(f"\nReport saved → {report_path}")


if __name__ == "__main__":
    main()