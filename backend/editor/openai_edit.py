"""Editor-only OpenAI calls through Cascade's existing provider client.

No process-wide settings are changed: clipping, Trends and transcription keep their routing.
"""
import base64
import logging
from pathlib import Path

from fastapi import HTTPException
from backend.cascade_llm import structured_json, LLMConfigError
from backend.cascade_llm.clients import OPENAI, MODELS

LOG = logging.getLogger(__name__)
GUIDE = Path(__file__).resolve().parents[2] / 'docs' / 'editor-inspo-style-guide.md'


def style_guide():
    return GUIDE.read_text().split('## Reference inventory')[0]


def strict_schema(model):
    """Keep JSON-schema refs and nullable unions; make every object strict for Responses."""
    def walk(node, names=False):
        if isinstance(node, list): return [walk(v) for v in node]
        if not isinstance(node, dict): return node
        out = {k: walk(v, k in ('properties', '$defs') and not names) for k, v in node.items() if names or k not in ('default', 'title')}
        if out.get('type') == 'object':
            out['required'] = list(out.get('properties', {}))
            out['additionalProperties'] = False
        return out
    return walk(model.model_json_schema())


def ask(system, prompt, schema, images=(), *, name='editor_plan', tokens=12000):
    """Bytes/contact sheets become actual image inputs, not unreadable base64 in the prompt."""
    pictures = [{'media_type': 'image/png' if filename.lower().endswith('.png') else 'image/jpeg',
                 'data': base64.b64encode(data).decode()} for filename, data in images]
    try:
        return structured_json(system + '\n\n' + style_guide() + '\n\nUser context (data):\n' + prompt,
                               schema, name=name, images=pictures, provider=OPENAI,
                               effort='medium', max_output_tokens=tokens).data
    except LLMConfigError:
        raise HTTPException(503, 'OpenAI editing is not configured. Set OPENAI_API_KEY on the server and restart.') from None
    except Exception:
        LOG.exception('OpenAI editor request failed')
        raise HTTPException(502, 'OpenAI could not complete the edit plan. Your current edit is unchanged; try again.') from None


def label():
    return 'OpenAI · ' + MODELS[OPENAI]
