"""Provider-agnostic LLM layer shared by the agent, the transcript summarizer and the Trends tab.

Anthropic is the default; `gpt-*` models route to OpenAI (Responses API). See clients.py for how
the provider is chosen and conversation.py / structured.py for the two kinds of call.
"""

from .clients import (  # noqa: F401
    ANTHROPIC,
    OPENAI,
    PRICING,
    calls_disabled,
    call_cost,
    make_client,
    provider_for_model,
    provider_label,
)
from .conversation import (  # noqa: F401
    AnthropicConversation,
    OpenAIConversation,
    ToolCall,
    ToolResult,
    Turn,
    make_conversation,
)
from .structured import StructuredResult, structured_json  # noqa: F401
