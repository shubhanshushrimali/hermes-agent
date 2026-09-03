"""Phone PWA is served from GET / on the mobile API server."""

from gateway.mobile_server import _PWA_PATH


def test_pwa_html_covers_chat_approve_steer():
    html = _PWA_PATH.read_text(encoding="utf-8")
    assert "Approve" in html
    assert "Deny" in html
    assert "/api/mobile/chat" in html
    assert "/api/mobile/steer" in html
    assert "/api/mobile/pending" in html
    assert "/api/mobile/approve" in html
    assert _PWA_PATH.is_file()
