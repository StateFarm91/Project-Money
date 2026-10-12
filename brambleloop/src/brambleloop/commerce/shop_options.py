"""Settings > Options as a registry: every control, its value, consequence and desired state (F-585).

`intel.etsy_surfaces` records that the Options page is readable through `getShop` and not
writable. `etsy.shop_snapshot` judged two of its controls (vacation, currency). F-585 asks
for every control, its current value, the business consequence, who may change it, the
desired state, and drift detection after Etsy changes the page. This is that registry.

- **API-observed controls** are read from the daily `getShop` snapshot.
- **Browser-only controls** come from the owner's dated reading of the page
  (`commerce.shop_observations`, page "options"); without one they are UNOBSERVED.
- **Drift** is any of: a value off its desired state; a value that changed since the last
  reading with no desired state to judge it (somebody changed it); or the page's control
  labels differing from the ones this registry knows -- which is how an Etsy UI or policy
  change shows up, because the registry would otherwise silently stop covering the page.

Every control's authority is the owner's: nothing here can or does write an option.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Control:
    key: str
    label: str
    api_field: str | None          # None: browser-only
    desired: Any                   # None: no desired state, any change is drift
    consequence: str
    authority: str = "owner"
    match: str = "equals"          # equals | startswith | falsy

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "api_field": self.api_field,
                "channel": "api" if self.api_field else "browser_only",
                "desired": self.desired, "consequence": self.consequence,
                "authority": self.authority}


CONTROLS: tuple[Control, ...] = (
    Control("vacation_mode", "Vacation mode", "is_vacation", False,
            "on means no buyer can purchase anything"),
    Control("vacation_autoreply", "Vacation auto-reply", "vacation_autoreply", None,
            "a stale auto-reply answers buyers with the wrong message", match="falsy"),
    Control("shop_currency", "Shop currency", "currency_code", "CAD",
            "every price decision here is computed in CAD"),
    Control("shop_language", "Shop language", "languages", "en",
            "listing copy is written in English", match="startswith"),
    Control("shop_country", "Shop location", "shop_location_country_iso", "CA",
            "Canadian tax, CASL and payout assumptions depend on it"),
    Control("shop_name", "Shop name", "shop_name", None,
            "the name is the brand on every listing and receipt"),
    Control("close_shop", "Close your shop", None, "open",
            "a closed shop removes every listing from sale"),
    Control("digital_download_delivery", "Digital download settings", None, None,
            "governs how buyers receive the PDF after purchase"),
)
BY_KEY = {c.key: c for c in CONTROLS}
KNOWN_LABELS = frozenset(c.label for c in CONTROLS)


def _judge(control: Control, value: Any) -> bool | None:
    """True on desired state, False off it, None when there is no desired state."""
    if control.match == "falsy":
        return not value if control.desired is None and value is not None else None
    if control.desired is None:
        return None
    if control.match == "startswith":
        values = value if isinstance(value, list) else [value]
        return any(str(v or "").lower().startswith(str(control.desired)) for v in values)
    return value == control.desired


def evaluate(shop: dict | None, previous_shop: dict | None = None,
             observation: dict | None = None) -> dict:
    """Every control with its current value, desired state and verdict."""
    controls_seen = ((observation or {}).get("values") or {}).get("controls") or {}
    labels_seen = ((observation or {}).get("values") or {}).get("labels")
    items, drift = [], []
    for c in CONTROLS:
        if c.api_field:
            observed = shop is not None and c.api_field in (shop or {})
            value = (shop or {}).get(c.api_field) if observed else None
            before = (previous_shop or {}).get(c.api_field) if previous_shop else None
            source = "getShop"
        else:
            observed = c.key in controls_seen
            value = controls_seen.get(c.key)
            before = None
            source = "owner observation" if observation else "none"
        verdict = _judge(c, value) if observed else None
        if not observed:
            status = "UNOBSERVED"
        elif verdict is False:
            status = "DRIFT"
        elif verdict is None and previous_shop is not None and c.api_field and \
                before is not None and before != value:
            status = "CHANGED"
        else:
            status = "OK" if verdict else "RECORDED"
        entry = {**c.to_dict(), "value": value, "status": status, "source": source}
        if status == "CHANGED":
            entry["was"] = before
        items.append(entry)
        if status in ("DRIFT", "CHANGED"):
            drift.append(c.key)
    ui_change = None
    if isinstance(labels_seen, list) and labels_seen:
        seen = set(map(str, labels_seen))
        browser_labels = {c.label for c in CONTROLS if not c.api_field}
        ui_change = {"new_labels": sorted(seen - KNOWN_LABELS),
                     "missing_labels": sorted(browser_labels - seen)}
        if ui_change["new_labels"] or ui_change["missing_labels"]:
            drift.append("options_page_changed")
    return {"controls": items, "drift": drift, "ui_change": ui_change,
            "unobserved": [i["key"] for i in items if i["status"] == "UNOBSERVED"]}
