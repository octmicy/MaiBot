"""桌宠独立会话以及只读参考的聊天流。"""

from typing import TYPE_CHECKING, Dict, List, Optional
from uuid import uuid4
import asyncio

from src.core.desktop_pet_chat import DESKTOP_PET_BOT_ID, DESKTOP_PET_PLATFORM, DESKTOP_PET_USER_ID
from src.core.internal_chat import INTERNAL_CHAT_PLATFORM
from src.core.local_operator import LOCAL_PLATFORM_BOT_IDS, PLUGIN_RELAY_CONFIG_KEY

if TYPE_CHECKING:
    from src.chat.message_receive.chat_manager import BotChatSession


def describe_conversation(session: "BotChatSession") -> Dict[str, str]:
    target = session.group_id or session.user_id or ""
    name = (session.group_name if session.group_id else session.user_cardname or session.user_nickname) or target
    return {
        "conversation_id": session.session_id,
        "name": name,
        "platform": session.platform,
        "target_id": target,
        "chat_type": "group" if session.group_id else "private",
    }


def require_current_conversation(current: str, expected: Optional[str]) -> None:
    if current != (expected or ""):
        raise ValueError("桌宠会话已切换，请确认当前会话后重新发送")


def resolve_conversation(session_id: str) -> "BotChatSession":
    from src.chat.message_receive.chat_manager import chat_manager

    session = chat_manager.get_existing_session_by_session_id(session_id)
    if session is None or session.platform == INTERNAL_CHAT_PLATFORM or session.platform in LOCAL_PLATFORM_BOT_IDS:
        raise ValueError("所选聊天会话已不存在或不可绑定")
    if not (session.group_id or session.user_id):
        raise ValueError("所选聊天会话缺少目标")
    return session


def find_desktop_pet_session(source_id: str) -> Optional["BotChatSession"]:
    from src.chat.message_receive.chat_manager import chat_manager

    sessions = chat_manager.resolve_sessions_by_target(
        platform=DESKTOP_PET_PLATFORM,
        target_id=DESKTOP_PET_USER_ID,
        chat_type="private",
    )
    return next(
        (
            session
            for session in sessions
            if session.account_id == DESKTOP_PET_BOT_ID and (session.scope or "") == source_id
        ),
        None,
    )


def is_desktop_pet_session(session: Optional["BotChatSession"]) -> bool:
    return bool(
        session is not None
        and session.platform == DESKTOP_PET_PLATFORM
        and session.user_id == DESKTOP_PET_USER_ID
        and not session.group_id
        and session.account_id == DESKTOP_PET_BOT_ID
    )


async def get_or_create_desktop_pet_session(source_id: str) -> "BotChatSession":
    from src.chat.message_receive.chat_manager import chat_manager
    from src.config.config import global_config

    if source_id:
        await asyncio.to_thread(resolve_conversation, source_id)
    require_current_conversation(global_config.desktop_pet.conversation_session_id, source_id)
    session = await chat_manager.get_or_create_session(
        DESKTOP_PET_PLATFORM,
        DESKTOP_PET_USER_ID,
        account_id=DESKTOP_PET_BOT_ID,
        scope=source_id or None,
    )
    require_current_conversation(global_config.desktop_pet.conversation_session_id, source_id)
    return session


async def submit_desktop_pet_message(source_id: str, text: str, images: List[Dict[str, str]]) -> str:
    from src.chat.message_receive.bot import chat_bot
    from src.webui.routers.chat.service import create_message_data, get_internal_chat_user_name

    user_name = await asyncio.to_thread(get_internal_chat_user_name)
    session = await get_or_create_desktop_pet_session(source_id)
    message_id = str(uuid4())
    packet = create_message_data(text, DESKTOP_PET_USER_ID, user_name, message_id=message_id, images=images)
    packet["account_id"] = DESKTOP_PET_BOT_ID
    packet["scope"] = session.scope
    info = packet["message_info"]
    info["platform"] = info["user_info"]["platform"] = DESKTOP_PET_PLATFORM
    info["additional_config"][PLUGIN_RELAY_CONFIG_KEY] = "builtin.desktop_pet"
    await chat_bot.message_process(packet, desktop_pet_session=session)
    return message_id
