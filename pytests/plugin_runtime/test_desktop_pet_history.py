from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.desktop_pet import service as pet_module
from src.desktop_pet.rendering import render_history_events
from src.desktop_pet.remote_server import validate_event
from src.desktop_pet.service import DesktopPetService
from src.maisaka.monitor import event_store


def test_remote_history_accepts_cursor_requests():
    validate_event({"type": "history", "request_id": "page-1", "cursors": {}})
    validate_event({"type": "history", "request_id": "page-2", "cursors": {"owner": 25}})


@pytest.mark.parametrize("cursors", [None, [], {"owner": -1}, {"owner": True}, {"owner": "25"},
                                    {str(index): 1 for index in range(101)}])
def test_remote_history_rejects_invalid_cursors(cursors):
    with pytest.raises(ValueError):
        validate_event({"type": "history", "request_id": "page", "cursors": cursors})


@pytest.mark.asyncio
async def test_history_reuses_monitor_cursor_and_only_loads_the_private_pet_session(monkeypatch):
    service = DesktopPetService()
    command = AsyncMock()
    monkeypatch.setattr(service, "_command", command)
    monkeypatch.setattr(pet_module.global_config.desktop_pet, "conversation_session_id", "qq-reference")
    lookup = Mock(return_value=SimpleNamespace(session_id="pet-session"))
    monkeypatch.setattr(pet_module, "find_desktop_pet_session", lookup)
    monkeypatch.setattr(service, "_can_stream_conversation", lambda: True)
    load = Mock(return_value=event_store.MonitorEventPage(
        events=[{"event": "message.sent", "data": {
            "event_id": 25, "message_id": "reply", "content": "历史回复", "media": [],
        }}], oldest_event_id=20, has_more=True,
    ))
    monkeypatch.setattr(event_store, "load_session_event_page", load)

    await service._publish_history({"request_id": "first", "cursors": {}})
    lookup.assert_called_once_with("qq-reference")
    load.assert_called_once_with(session_id="pet-session", before_event_id=0)
    response = command.await_args.args[0]
    assert response["conversation_id"] == "qq-reference"
    assert response["cursors"] == {"pet-session": 20}
    assert response["has_more"]
    assert response["items"] == [{"id": "reply", "who": "mai",
                                  "parts": [{"kind": "text", "text": "历史回复"}]}]

    load.reset_mock()
    load.return_value = event_store.MonitorEventPage(events=[], oldest_event_id=0, has_more=False)
    await service._publish_history({"request_id": "older", "cursors": {"pet-session": 20, "qq-reference": 99}})
    load.assert_called_once_with(session_id="pet-session", before_event_id=20)
    assert command.await_args.args[0]["has_more"] is False


@pytest.mark.asyncio
async def test_history_failure_is_reported_without_advancing_cursor(monkeypatch):
    service = DesktopPetService()
    command = AsyncMock()
    monkeypatch.setattr(service, "_command", command)
    monkeypatch.setattr(pet_module.global_config.desktop_pet, "conversation_session_id", "")
    monkeypatch.setattr(pet_module, "find_desktop_pet_session", Mock(return_value=SimpleNamespace(session_id="pet-session")))
    monkeypatch.setattr(event_store, "load_session_event_page", Mock(side_effect=RuntimeError("database unavailable")))
    await service._publish_history({"request_id": "failed", "cursors": {"pet-session": 20}})
    assert command.await_args.args[0] == {
        "type": "history", "request_id": "failed", "error": "database unavailable",
    }


def test_history_renders_messages_and_merges_media_updates():
    events = [
        {"event": "planner.started", "data": {}},
        {"event": "message.ingested", "data": {"message_id": "user", "content": "处理中"}},
        {"event": "message.updated", "data": {"message_id": "user", "content": "图片内容"}},
        {"event": "message.sent", "data": {"message_id": "bot", "content": "收到"}},
    ]
    items = render_history_events(events)
    assert [item["id"] for item in items] == ["user", "bot"]
    assert items[0]["parts"] == [{"kind": "text", "text": "图片内容"}]
    assert [item["who"] for item in items] == ["me", "mai"]
