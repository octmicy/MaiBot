from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.chat.message_receive.chat_manager import BotChatSession
from src.desktop_pet import conversation
from src.desktop_pet.conversation import describe_conversation, require_current_conversation


@pytest.mark.parametrize(
    ("group_id", "group_name", "user_id", "nickname", "expected_name", "expected_id"),
    [
        ("123456", "麦麦群", None, None, "麦麦群", "123456"),
        (None, None, "11112222", "麦麦朋友", "麦麦朋友", "11112222"),
    ],
)
def test_describe_reference_uses_the_real_chat_name(
    group_id, group_name, user_id, nickname, expected_name, expected_id
):
    session = BotChatSession(
        "source",
        "qq",
        group_id=group_id,
        group_name=group_name,
        user_id=user_id,
        user_nickname=nickname,
    )
    description = describe_conversation(session)
    assert description["name"] == expected_name
    assert description["target_id"] == expected_id
    assert description["conversation_id"] == "source"


def test_stale_and_legacy_clients_cannot_send_to_the_new_target():
    require_current_conversation("", None)
    require_current_conversation("", "")
    require_current_conversation("existing", "existing")
    for expected in (None, "", "former"):
        with pytest.raises(ValueError, match="会话"):
            require_current_conversation("existing", expected)
    with pytest.raises(ValueError, match="会话"):
        require_current_conversation("", "former")


def test_pet_conversations_cannot_be_selected_as_reference(monkeypatch):
    from src.chat.message_receive.chat_manager import chat_manager

    pet = BotChatSession("pet-chat", "desktop_pet", user_id="owner", account_id="self", scope="source")
    monkeypatch.setattr(chat_manager, "get_existing_session_by_session_id", Mock(return_value=pet))
    with pytest.raises(ValueError, match="不可绑定"):
        conversation.resolve_conversation("pet-chat")


@pytest.mark.asyncio
async def test_desktop_pet_uses_its_own_sessions_for_each_reference_and_default(monkeypatch):
    from src.chat.message_receive import bot as bot_module
    from src.chat.message_receive.chat_manager import ChatManager
    from src.webui.routers.chat import service

    manager = ChatManager()
    sources = {
        "group": BotChatSession("group", "qq", group_id="123456", group_name="麦麦群", account_id="external-bot"),
        "private": BotChatSession(
            "private", "qq", user_id="12345", user_nickname="麦麦朋友", account_id="external-bot"
        ),
    }
    manager.sessions.update(sources)
    monkeypatch.setattr(manager, "_save_session", Mock())
    monkeypatch.setattr(import_module("src.chat.message_receive.chat_manager"), "chat_manager", manager)
    monkeypatch.setattr(bot_module, "chat_manager", manager)
    monkeypatch.setattr(service, "get_internal_chat_user_name", lambda: "主人")
    broadcast = AsyncMock()
    monkeypatch.setattr(service.chat_manager, "broadcast_to_group", broadcast)

    bot = bot_module.ChatBot()
    monkeypatch.setattr(bot_module, "chat_bot", bot)
    monkeypatch.setattr(bot, "_ensure_started", AsyncMock())
    monkeypatch.setattr(
        bot, "_invoke_message_hook", AsyncMock(side_effect=lambda _hook, msg: (SimpleNamespace(aborted=False), msg))
    )
    monkeypatch.setattr("src.files.service.get_file_service", lambda: SimpleNamespace(ingest=AsyncMock()))
    receive = AsyncMock()
    monkeypatch.setattr(bot.heartflow_message_receiver, "process_message", receive)

    config = bot_module.global_config.desktop_pet
    pet_sessions = []
    for source in ("group", "private", "", "group"):
        monkeypatch.setattr(config, "conversation_session_id", source)
        message_id = await conversation.submit_desktop_pet_message(source, "这句仅在桌宠里显示", [])
        message = receive.await_args.args[0]
        pet_sessions.append(message.session_id)
        assert message.message_id == message_id
        assert message.platform == "desktop_pet"
        assert message.account_id == "self"
        assert message.scope == (source or None)
        assert message.message_info.user_info.user_id == "owner"
        assert message.message_info.group_info is None
        assert message.message_info.additional_config["relayed_by_plugin"] == "builtin.desktop_pet"
        assert manager.sessions[message.session_id].scope == (source or None)

    assert len(set(pet_sessions)) == 3
    assert pet_sessions[0] == pet_sessions[-1]
    assert all(source not in manager.last_messages for source in sources)
    assert sources["group"].group_name == "麦麦群"
    assert sources["private"].user_nickname == "麦麦朋友"
    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_desktop_pet_rechecks_reference_after_message_processing(monkeypatch):
    from src.chat.message_receive import bot as bot_module
    from src.chat.message_receive.chat_manager import chat_manager
    from src.webui.routers.chat import service

    bot = bot_module.ChatBot()
    monkeypatch.setattr(bot_module, "chat_bot", bot)
    config = bot_module.global_config.desktop_pet
    monkeypatch.setattr(config, "conversation_session_id", "session-a")
    pet = BotChatSession("pet-a", "desktop_pet", user_id="owner", account_id="self", scope="session-a")
    monkeypatch.setattr(chat_manager, "get_or_create_session", AsyncMock(return_value=pet))
    monkeypatch.setattr(conversation, "resolve_conversation", Mock())
    monkeypatch.setattr(service, "get_internal_chat_user_name", lambda: "主人")
    register = Mock(side_effect=AssertionError("stale message reached registration"))
    monkeypatch.setattr(chat_manager, "register_message", register)

    async def switch_after_process(hook, message):
        if hook == "chat.receive.after_process":
            config.conversation_session_id = "session-b"
        return SimpleNamespace(aborted=False), message

    monkeypatch.setattr(bot, "_invoke_message_hook", switch_after_process)
    with pytest.raises(ValueError, match="会话已切换"):
        await conversation.submit_desktop_pet_message("session-a", "测试", [])
    register.assert_not_called()


@pytest.mark.asyncio
async def test_desktop_pet_reply_is_saved_locally_without_contacting_an_adapter(monkeypatch):
    from src.chat.message_receive.chat_manager import chat_manager
    from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
    from src.desktop_pet.service import desktop_pet_service
    from src.platform_io.manager import PlatformIOManager
    from src.plugin_runtime.host.hook_dispatcher import HookDispatchResult
    from src.services import send_service

    broker = PlatformIOManager()
    drivers = Mock(side_effect=AssertionError("desktop pet reply tried an adapter"))
    monkeypatch.setattr(broker, "resolve_drivers", drivers)
    monkeypatch.setattr(send_service, "get_platform_io_manager", lambda: broker)
    pet = BotChatSession("pet-chat", "desktop_pet", user_id="owner", account_id="self", scope="qq-group")
    monkeypatch.setitem(chat_manager.sessions, pet.session_id, pet)
    save = AsyncMock()
    notify = AsyncMock()
    sync_history = Mock()
    monkeypatch.setattr(send_service, "_store_sent_message", save)
    monkeypatch.setattr(send_service, "_sync_sent_message_to_maisaka_history", sync_history)
    monkeypatch.setattr(desktop_pet_service, "notify_reply", notify)

    async def hook(name, *, message, **kwargs):
        # A rewritten outbound message still uses the host's private route.
        if name == "send_service.before_send":
            message = {**message, "platform": "qq", "scope": "external", "session_id": "qq-group"}
        return HookDispatchResult(name, {"message": message, **kwargs})

    monkeypatch.setattr(send_service, "_get_runtime_manager", lambda: SimpleNamespace(invoke_hook=hook))
    reply = await send_service._send_to_target_with_message(
        MessageSequence([TextComponent("只在桌宠回复")]),
        pet.session_id,
        sync_to_maisaka_history=True,
    )

    assert reply is not None
    assert reply.platform == "desktop_pet"
    assert reply.scope == "qq-group"
    assert reply.session_id == pet.session_id
    save.assert_awaited_once_with(reply)
    sync_history.assert_called_once()
    assert notify.await_args.args[0]["session_id"] == pet.session_id
    drivers.assert_not_called()
