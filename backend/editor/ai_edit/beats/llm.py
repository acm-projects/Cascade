"""The one place the beats pipeline talks to a model: the Anthropic API.

The model name comes from AI_EDITOR_MODEL and the key from ANTHROPIC_API_KEY (both environment
variables, read at call time). Nothing else in beats/ knows which model answers.
"""
import json
import logging
import os
import re

LOG = logging.getLogger(__name__)
ENV_MODEL = 'AI_EDITOR_MODEL'
MAX_TOKENS = 32000


class PlanError(Exception):
    """A planning failure. `user_message` is safe to show in the chat; `detail` is for the logs."""

    def __init__(self, user_message, detail=''):
        super().__init__(detail or user_message)
        self.user_message = user_message
        self.detail = detail or user_message


def model():
    name = os.getenv(ENV_MODEL, '').strip()
    if not name:
        raise PlanError('The AI editor is not set up on this server yet.', f'{ENV_MODEL} is not set.')
    return name


def complete(system, messages, max_tokens=MAX_TOKENS):
    """Send `messages` with `system` as the system prompt and return the reply text."""
    from backend.cascade_llm.clients import ANTHROPIC, LLMConfigError, make_client
    name = model()
    try:
        client = make_client(ANTHROPIC)
    except LLMConfigError as exc:
        raise PlanError('The AI editor is not set up on this server yet.', str(exc)) from None
    try:
        with client.messages.stream(model=name, max_tokens=max_tokens, system=system, messages=messages) as stream:
            message = stream.get_final_message()
    except Exception as exc:   # network, rate limit, bad model name: the caller keeps the current plan
        LOG.warning('AI editor request failed', exc_info=True)
        raise PlanError('The AI editor could not be reached. Your current edit is unchanged; try again.', f'{type(exc).__name__}: {exc}') from None
    if getattr(message, 'stop_reason', None) == 'max_tokens':
        LOG.warning('AI editor reply was cut off at %s tokens', max_tokens)
    return ''.join(block.text for block in message.content if getattr(block, 'type', '') == 'text')


FENCE = re.compile(r'^\s*```[a-zA-Z]*\s*\n(.*?)\n\s*```\s*$', re.S)


def parse_json(text):
    """The JSON object in a model reply: code fences stripped, surrounding chatter ignored. Raises ValueError."""
    text = (text or '').strip()
    fenced = FENCE.match(text)
    if fenced: text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find('{'), text.rfind('}')
        if start < 0 or end <= start: raise ValueError('no JSON object in the reply') from None
        data = json.loads(text[start:end+1])
    if not isinstance(data, dict): raise ValueError('the reply is JSON but not an object')
    return data
