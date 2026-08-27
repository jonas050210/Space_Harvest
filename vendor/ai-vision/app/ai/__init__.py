"""AI vision layer: engine, context, commands, conversation, events, voice."""

from app.ai.commands import COMMANDS, answer_command, match_command
from app.ai.context import SYSTEM_PROMPT, build_scene_context
from app.ai.conversation import ChatMessage, VisionConversation
from app.ai.engine import AIVisionEngine
from app.ai.events import EventType, SceneMonitor, VisionEvent
from app.ai.reactions import ReactionEngine, match_watch_request
from app.ai.voice import (
    SpeechToTextProvider,
    TextToSpeechProvider,
    VoiceCommandPipeline,
    VoiceEngine,
)

__all__ = [
    "AIVisionEngine",
    "SYSTEM_PROMPT",
    "build_scene_context",
    "VisionConversation",
    "ChatMessage",
    "COMMANDS",
    "match_command",
    "answer_command",
    "SceneMonitor",
    "VisionEvent",
    "EventType",
    "ReactionEngine",
    "match_watch_request",
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "VoiceCommandPipeline",
    "VoiceEngine",
]
