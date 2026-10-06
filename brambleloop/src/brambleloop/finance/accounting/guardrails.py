"""What the Accountant agent must never be able to do (F-917).

Enforced by *absence*: the accounting package has no function that files a return, pays,
transfers, withdraws, borrows, signs, or changes bank details, and imports no network or
payment client. `audit_package()` checks that statically (names and imports of every module
in the package) and a test asserts it stays true. `refuse(action)` is what a caller gets if
it asks Finance to do one of these things: a refusal, never an attempt.
"""
from __future__ import annotations

import ast
import pkgutil
import re
from pathlib import Path

FORBIDDEN_ACTIONS = ("file_tax", "submit_return", "remit", "pay", "transfer", "withdraw",
                     "wire", "send_money", "payout_request", "borrow", "loan", "sign_contract",
                     "change_bank", "set_bank", "update_bank", "open_account", "apply_credit")
# Name fragments no public callable in the package may carry.
_FORBIDDEN_NAME = re.compile(
    r"(^|_)(file_tax|file_return|submit|remit|pay|payment_send|transfer|withdraw|wire|"
    r"send_money|borrow|loan|sign|contract|bank_details|change_bank|set_bank|update_bank|"
    r"disburse|charge_card)(_|$)")
# Modules that would give the package a way to reach the outside world.
_FORBIDDEN_IMPORTS = ("requests", "httpx", "urllib", "socket", "http.client", "aiohttp",
                      "stripe", "smtplib", "ftplib", "paramiko",
                      "brambleloop.integrations", "brambleloop.gateway")


class AccountingAuthorityRefused(PermissionError):
    pass


def refuse(action: str) -> None:
    raise AccountingAuthorityRefused(
        f"Finance cannot {action!r}: the Accountant agent has no authority or capability to "
        "file taxes, move money, change bank details, borrow, sign contracts or make "
        "regulated professional representations. Prepare the evidence and route it to the "
        "owner / a licensed professional.")


def audit_package() -> dict:
    """Static audit of every module in `finance.accounting`."""
    here = Path(__file__).parent
    names, imports, modules = [], [], []
    for info in pkgutil.iter_modules([str(here)]):
        path = here / f"{info.name}.py"
        if not path.exists():
            continue
        modules.append(info.name)
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_") and _FORBIDDEN_NAME.search(node.name.lower()):
                    names.append(f"{info.name}.{node.name}")
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if any(a.name == f or a.name.startswith(f + ".") for f in _FORBIDDEN_IMPORTS):
                        imports.append(f"{info.name}: import {a.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = ("." * node.level) + (node.module or "")
                resolved = mod.lstrip(".")
                if node.level >= 3:  # from ...x -> brambleloop.x
                    resolved = "brambleloop." + resolved
                if any(resolved == f or resolved.startswith(f + ".")
                       for f in _FORBIDDEN_IMPORTS):
                    imports.append(f"{info.name}: from {mod} import ...")
    return {"modules": sorted(modules), "forbidden_names": names,
            "forbidden_imports": imports, "ok": not names and not imports}
