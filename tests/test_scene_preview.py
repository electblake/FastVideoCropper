from fastvideocropper import app


def test_scene_preview_follows_scan_and_respects_toggle(
    qtbot, tmp_path, monkeypatch, source
):
    monkeypatch.setattr(app, "user_config_path", lambda *args, **kwargs: tmp_path)
    c = app.Application()
    qtbot.addWidget(c.window)
    c.window.show()
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    arguments = app.SceneScan.arguments
    monkeypatch.setattr(
        app.SceneScan, "arguments", lambda self: ["-re", *arguments(self)]
    )
    c.preview.setChecked(True)
    c.detect_segments(1, 0, framestep=30, threads=1)
    qtbot.waitUntil(lambda: c.player.position() >= 500, timeout=5000)
    qtbot.waitUntil(
        lambda: c.video.videoSink().videoFrame().startTime() >= 400000,
        timeout=5000,
    )
    assert c.seek.value() == c.player.position()
    assert not c.transport.isEnabled()
    c.preview.setChecked(False)
    position = c.player.position()
    progress = c.progress.value()
    qtbot.waitUntil(lambda: c.progress.value() > progress, timeout=3000)
    assert c.player.position() == position
    c.preview.setChecked(True)
    qtbot.waitUntil(lambda: c.player.position() > position, timeout=3000)
    c.cancel.click()
    qtbot.waitUntil(lambda: not c.running, timeout=3000)
    assert c.progress_text.text() == "Scene detection canceled"
    assert c.transport.isEnabled()
    c.window.close()
