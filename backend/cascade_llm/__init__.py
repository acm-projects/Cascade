"""LLM layer shared by the agent, the transcript summarizer and the Trends tab.

LLM_PROVIDER=anthropic (default) or openai picks the provider for everything; the model is fixed
per provider. See clients.py. conversation.py is the agent loop's wire format per provider and
structured.py is the "prompt in, schema-shaped JSON out" call.
"""

from .clients import (  # noqa: F401
    ANTHROPIC,
    MODELS,
    OPENAI,
    PRICING,
    call_cost,
    make_client,
    selected_model,
    selected_provider,
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
