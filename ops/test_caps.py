import csv, pathlib, sys, tempfile, importlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import caps
def write_ledger(rows):
    p = pathlib.Path(tempfile.mkdtemp()) / "L.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id","datetime_utc","description","business_product_channel","revenue_cad","expense_cad","platform_payment_fees_cad","advertising_cad","refunds_chargebacks_cad","net_contribution_cad","running_available_cash_cad","capital_deployed_committed_cad","evidence_ref"]); w.writeheader()
        for r in rows: w.writerow({**{k: "0" for k in w.fieldnames}, **r})
    return p
def test_allows_within_caps():
    caps.LEDGER = write_ledger([{"id":"1","business_product_channel":"B: meta ads","advertising_cad":"100"}])
    assert caps.assert_within_cap("B", 50)
def test_refuses_over_ads_cap():
    caps.LEDGER = write_ledger([{"id":"1","business_product_channel":"B: meta ads","advertising_cad":"380"}])
    try: caps.assert_within_cap("B", 30); assert False
    except ValueError as e: assert "ads cap" in str(e)
def test_refuses_reserve_breach():
    caps.LEDGER = write_ledger([{"id":"1","business_product_channel":"A: etsy","expense_cad":"230"},{"id":"2","business_product_channel":"B: tools","expense_cad":"100"},{"id":"3","business_product_channel":"B: meta ads","advertising_cad":"300"}])
    try: caps.assert_within_cap("B", 90); assert False
    except ValueError as e: assert "reserve" in str(e) or "total cap" in str(e)
def test_untracked_rows_count_against_bankroll_only():
    caps.LEDGER = write_ledger([{"id":"1","business_product_channel":"n/a","expense_cad":"0"}])
    assert caps.spend_by_track()["other"] == 0.0 and caps.assert_within_cap("A", 40)
if __name__ == "__main__":
    fails = 0
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            try: f(); print("OK ", n)
            except Exception as e: fails += 1; print("FAIL", n, repr(e))
    sys.exit(1 if fails else 0)
