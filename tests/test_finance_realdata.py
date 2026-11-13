"""Regression tests for real-export problems found in the readiness audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from runtime.finance import analyze, load_context, load_ledger, record_driver
from runtime.finance.__main__ import main as cli
from runtime.finance.ledger import infer_dayfirst

ROOT = Path(__file__).resolve().parents[1]


def _misa_rows() -> list[list[str]]:
    """MISA-style VAS export: title rows, dd/mm/yyyy, VND with '.' thousands, 911 closing."""
    rows = [["CÔNG TY TNHH ABC", "", "", "", "", ""], ["SỔ NHẬT KÝ CHUNG", "", "", "", "", ""],
            ["Từ ngày 01/11/2025 đến 31/12/2025", "", "", "", "", ""],
            ["Ngày hạch toán", "Số chứng từ", "Diễn giải", "Tài khoản", "Phát sinh Nợ",
             "Phát sinh Có"]]

    def je(d: str, no: str, desc: str, dr: str, cr: str, amt: int) -> None:
        v = f"{amt:,.0f}".replace(",", ".")
        rows.extend([[d, no, desc, dr, v, ""], [d, no, desc, cr, "", v]])

    je("05/11/2025", "BH001", "Bán hàng", "131", "5111", 1_200_000_000)
    je("05/11/2025", "XK001", "Giá vốn", "632", "1561", 700_000_000)
    je("10/12/2025", "BH002", "Bán hàng", "131", "5111", 1_500_000_000)
    je("10/12/2025", "XK002", "Giá vốn", "632", "1561", 800_000_000)
    je("15/12/2025", "CP001", "Lương QL", "6421", "334", 150_000_000)
    je("31/12/2025", "KC01", "Kết chuyển DT", "5111", "911", 1_500_000_000)
    je("31/12/2025", "KC02", "Kết chuyển GV", "911", "632", 800_000_000)
    je("31/12/2025", "KC03", "Kết chuyển CP", "911", "6421", 150_000_000)
    return rows


@pytest.fixture()
def misa_xlsx(tmp_path: Path) -> Path:
    path = tmp_path / "misa.xlsx"
    pd.DataFrame(_misa_rows()).to_excel(path, index=False, header=False)
    return path


def test_misa_export_end_to_end(misa_xlsx: Path) -> None:
    a = analyze(misa_xlsx, scheme="vas", anomalies=False)
    assert a.load_report.header_row == 3  # title rows skipped above the header
    assert a.settings["dayfirst"] is True and a.settings["decimal"] == ","
    # Correct month (05/11 = 5 Nov, not 11 May), correct VND magnitude, 911 removed.
    assert a.pnl.loc["net_revenue", "2025-11"] == 1_200_000_000
    assert a.pnl.loc["net_revenue", "2025-12"] == 1_500_000_000
    assert a.pnl.loc["net_income", "2025-12"] == 550_000_000
    codes = {f.code for f in a.validation.findings}
    assert "closing_entries_removed" in codes and "materiality_scale" in codes
    assert "round_amounts" not in codes  # VND: whole thousands are normal


def test_without_closing_exclusion_pnl_is_zeroed(misa_xlsx: Path) -> None:
    a = analyze(misa_xlsx, scheme="vas", closing_accounts=[], anomalies=False)
    assert a.pnl.loc["net_revenue", "2025-12"] == 0  # proves why the default matters


def test_date_order_inference() -> None:
    assert infer_dayfirst(pd.Series(["05/11/2025", "15/12/2025"])) is True
    assert infer_dayfirst(pd.Series(["11/05/2025", "12/15/2025"])) is False
    assert infer_dayfirst(pd.Series(["01/02/2025"])) is None
    _, rep = load_ledger(pd.DataFrame({"Date": ["01/02/2025"], "Account": ["4000"],
                                       "Amount": ["1"]}))
    assert any("ambiguous" in w for w in rep.warnings)


def test_ytd_tb_detected_and_converted() -> None:
    tb = pd.DataFrame({"Period": ["2026-01"] * 2 + ["2026-02"] * 2 + ["2026-03"] * 2,
                       "Account": ["4000", "5000"] * 3,
                       "Balance": [-100.0, 60.0, -210.0, 125.0, -300.0, 190.0]})
    a = analyze(tb, expect_balanced=False, anomalies=False)
    assert "possible_cumulative_tb" in {f.code for f in a.validation.findings}
    b = analyze(tb, expect_balanced=False, anomalies=False, cumulative=True)
    assert b.pnl.loc["revenue", ["2026-01", "2026-02", "2026-03"]].tolist() == [100, 110, 90]


def test_mixed_currency_blocks() -> None:
    mc = pd.DataFrame({"Date": ["2026-01-05"] * 4, "Account": ["4000", "1200"] * 2,
                       "Debit": [0, 100, 0, 2_500_000], "Credit": [100, 0, 2_500_000, 0],
                       "Currency": ["USD", "USD", "VND", "VND"]})
    a = analyze(mc, anomalies=False)
    assert not a.validation.ok and a.confidence.startswith("low")


def test_context_drives_settings_and_commentary(tmp_path: Path, misa_xlsx: Path) -> None:
    ctx = tmp_path / "fpa-context"
    assert cli(["init-context", str(ctx), "--scheme", "vas", "--currency", "VND"]) == 0
    cfg = (ctx / "company.yaml").read_text(encoding="utf-8")
    assert "scheme: vas" in cfg and 'closing_accounts: ["911"]' in cfg
    (ctx / "company.yaml").write_text(cfg.replace("abs: 10000", "abs: 100000000")
                                      .replace("owners: {}", "owners:\n  cogs: Supply Chain Lead"),
                                      encoding="utf-8")
    record_driver(ctx, "2025-12", "revenue", "Year-end promo", "Head of Sales")
    with pytest.raises(ValueError):
        record_driver(ctx, "2025-12", "revenue", "x", "  ")
    a = analyze(misa_xlsx, context=ctx, anomalies=False)
    assert a.settings["scheme"] == "vas" and "100,000,000" in a.settings["materiality"]
    text = " ".join(a.commentary)
    assert "Year-end promo (confirmed by Head of Sales)" in text
    assert "confirm with Supply Chain Lead" in text
    assert "no_context" not in {f.code for f in a.validation.findings}
    # init-context never overwrites existing knowledge.
    cli(["init-context", str(ctx)])
    assert "100000000" in (ctx / "company.yaml").read_text(encoding="utf-8")


def test_context_validation_errors(tmp_path: Path) -> None:
    (tmp_path / "company.yaml").write_text("owners:\n  marketing: X\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown P&L lines"):
        load_context(tmp_path)


def test_cli_json_has_full_payload(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    code = cli(["analyze", "--gl", str(ROOT / "examples/finance/sample_gl.csv"),
                "--json-out", str(out)])
    assert code == 2
    d = json.loads(out.read_text(encoding="utf-8"))
    assert {"pnl", "variance", "evidence", "review_queue", "settings", "unmapped_accounts"} <= set(d)
    assert any(r["index"] == "net_income" for r in d["pnl"])


def test_cli_reconcile(tmp_path: Path) -> None:
    bank = tmp_path / "bank.csv"
    pd.DataFrame({"Date": ["2026-09-01", "2026-09-30"], "Description": ["DEP Acme", "Bank fee"],
                  "Deposit": ["1,000.00", ""], "Withdrawal": ["", "15.00"]}).to_csv(bank, index=False)
    gl = tmp_path / "gl.csv"
    pd.DataFrame({"Date": ["2026-09-01", "2026-09-01"], "Account": ["1000", "4000"],
                  "Debit": [1000, 0], "Credit": [0, 1000], "Memo": ["Acme", "Acme"]}).to_csv(gl, index=False)
    out = tmp_path / "rec.json"
    code = cli(["reconcile", "--bank", str(bank), "--gl", str(gl), "--cash-account", "1000",
                "--bank-balance", "985", "--gl-balance", "1000", "--json-out", str(out)])
    s = json.loads(out.read_text(encoding="utf-8"))["summary"]
    assert code == 2 and s["match_rate_pct"] == 50.0 and s["reconciled"]


def test_vendored_engine_in_sync() -> None:
    r = subprocess.run([sys.executable, str(ROOT / "scripts/sync_skill_engine.py"), "--check"],
                       capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_skill_launcher_is_self_contained(tmp_path: Path) -> None:
    """Run the skill's own launcher in isolated mode from an unrelated directory."""
    r = subprocess.run(
        [sys.executable, "-I", str(ROOT / "skills/fpa/scripts/fpa.py"), "analyze", "--gl",
         str(ROOT / "examples/finance/sample_gl.csv"), "--json"],
        capture_output=True, text=True, cwd=tmp_path, check=False)
    assert r.returncode == 2, r.stderr
    assert json.loads(r.stdout)["period"] == "2026-09"


def test_plugin_manifests() -> None:
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert plugin["name"] == market["plugins"][0]["name"]
    for skill in ("fpa", "resilience"):
        head = (ROOT / f"skills/{skill}/SKILL.md").read_text(encoding="utf-8").split("---")
        assert head[0] == "" and "name:" in head[1] and "description:" in head[1]
