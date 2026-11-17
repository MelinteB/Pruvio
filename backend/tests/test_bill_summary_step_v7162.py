"""Only the active bill step is rendered; Next never scrolls past item selection."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def test_summary_is_exclusive_route_driven_step():
    source=(ROOT/'frontend/src/Bill.jsx').read_text(encoding='utf-8')
    assert "requested === 'summary' ? 'summary'" in source
    assert "{section==='items'&&<div id=\"core-bill-items\"" in source
    assert "{section==='summary'&&<div className=\"pruvs-bill-summary-screen\"" in source
    assert "{section==='summary'?<nav className=\"pruvs-bill-summary-nav\"" in source
    assert "Back to item selection" in source
    assert "chooseSection('summary')" in source
    assert "requested !== 'summary'" not in source
    assert "scrollIntoView" in source  # owner controls still accessible


def test_next_uses_server_confirm_and_changes_step_only_after_success():
    source=(ROOT/'frontend/src/Bill.jsx').read_text(encoding='utf-8')
    handler=source.split("async function nextToSummary() {",1)[1].split("\n  async function select(",1)[0]
    assert "selection/complete" in handler
    assert "setData(await send(" in handler
    assert "chooseSection('summary')" in handler
    assert handler.index("chooseSection('summary')")>handler.index("catch (e)")
    assert "setError(" in handler
    assert "payment" not in handler.split("setData(await send(",1)[1].split(");",1)[0]


def test_summary_layout_is_not_inline_under_item_selection():
    css=(ROOT/'frontend/src/floating-bill-workspace.css').read_text(encoding='utf-8')
    assert ".pruvs-bill-summary-screen" in css
    assert ".pruvs-bill-summary-nav" in css
