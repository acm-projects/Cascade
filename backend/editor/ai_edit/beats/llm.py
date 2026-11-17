"""The one place the beats pipeline talks to a model: Anthropic or OpenAI.

AI_EDITOR_PROVIDER picks the provider: "anthropic" or "openai". Unset: Anthropic when ANTHROPIC_API_KEY is
set, else OpenAI. Anthropic uses AI_EDITOR_MODEL; OpenAI uses AI_EDITOR_OPENAI_MODEL (default: the model the
rest of Cascade uses for OpenAI). Keys: ANTHROPIC_API_KEY / OPENAI_API_KEY. All read at call time. Nothing
else in beats/ knows which model answers.
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


def provider():
    chosen = os.getenv('AI_EDITOR_PROVIDER', '').strip().lower()
    if chosen in ('anthropic', 'openai'): return chosen
    return 'anthropic' if os.getenv('ANTHROPIC_API_KEY', '').strip() else 'openai'


def model():
    if provider() == 'openai':
        from backend.cascade_llm.clients import MODELS, OPENAI
        return os.getenv('AI_EDITOR_OPENAI_MODEL', '').strip() or MODELS[OPENAI]
    name = os.getenv(ENV_MODEL, '').strip()
    if not name:
        raise PlanError('The AI editor is not set up on this server yet.', f'{ENV_MODEL} is not set.')
    return name


def complete(system, messages, max_tokens=MAX_TOKENS):
    """Send `messages` with `system` as the system prompt and return the reply text."""
    if provider() == 'openai': return _openai(system, messages, max_tokens)
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


def _openai(system, messages, max_tokens):
    """The same conversation through OpenAI's Responses API, answering in JSON mode."""
    from backend.cascade_llm.clients import OPENAI, LLMConfigError, make_client
    name = model()
    try:
        client = make_client(OPENAI)
    except LLMConfigError as exc:
        raise PlanError('The AI editor is not set up on this server yet.', str(exc)) from None
    turns = [{'role': m['role'], 'content': m['content']} for m in messages]
    turns[-1] = {**turns[-1], 'content': turns[-1]['content']+'\n\nReturn only the JSON object.'}
    try:
        response = client.responses.create(model=name, store=False, instructions=system, input=turns,
                                           text={'format': {'type': 'json_object'}},
                                           reasoning={'effort': os.getenv('AI_EDITOR_EFFORT', 'medium')},
                                           max_output_tokens=max_tokens)
    except Exception as exc:   # network, quota, bad model name: the caller keeps the current plan
        LOG.warning('AI editor request failed', exc_info=True)
        raise PlanError('The AI editor could not be reached. Your current edit is unchanged; try again.', f'{type(exc).__name__}: {exc}') from None
    if getattr(response, 'status', None) == 'incomplete':
        LOG.warning('AI editor reply was cut off: %s', getattr(response, 'incomplete_details', None))
    text = ''
    for item in getattr(response, 'output', None) or []:
        if getattr(item, 'type', None) != 'message': continue
        for part in getattr(item, 'content', None) or []:
            if getattr(part, 'type', None) == 'output_text': text += part.text
    return text


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
