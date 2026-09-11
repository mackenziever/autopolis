def test_viewer_3d_loads_replay(page, viewer_base_url, replay_path):
    page.goto(f"{viewer_base_url}/viewer_3d.html", wait_until="networkidle")
    page.locator("#file").set_input_files(str(replay_path))
    page.wait_for_function(
        "() => document.getElementById('hud') && document.getElementById('hud').innerText.includes('acting')",
        timeout=30_000,
    )
    hud = page.locator("#hud").inner_text()
    assert "DAY" in hud
    assert "acting" in hud
    assert "learning" in hud
    assert page.locator("#tick").inner_text().startswith("tick")
    assert "CITY SIM" in page.locator("#titleHud").inner_text()
    page.wait_for_selector("#view canvas", timeout=10_000)
    page.locator("#play").click()
    assert "Pausa" in page.locator("#play").inner_text() or "⏸" in page.locator("#play").inner_text()
    page.screenshot(path="qa/live/viewer_3d_play.png", full_page=True)
