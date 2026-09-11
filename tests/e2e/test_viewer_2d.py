def test_viewer_2d_loads_replay(page, viewer_base_url, replay_path):
    page.goto(f"{viewer_base_url}/replay_viewer.html", wait_until="domcontentloaded")
    page.locator("#file").set_input_files(str(replay_path))
    page.wait_for_function(
        "() => document.getElementById('hud') && document.getElementById('hud').innerText.includes('agenti')",
        timeout=15_000,
    )
    assert "agenti" in page.locator("#hud").inner_text()
    assert page.locator("#tick").inner_text().startswith("tick")
    assert page.locator("canvas#c").count() == 1
    page.locator("#play").click()
    assert "Pausa" in page.locator("#play").inner_text() or "⏸" in page.locator("#play").inner_text()
