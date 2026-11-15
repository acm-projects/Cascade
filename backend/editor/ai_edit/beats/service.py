"""Stage 2: the director and critic service.

    make_plan(transcript, window=None, instructions=None) -> PlanResult
    revise_plan(plan, transcript, message) -> PlanResult

The prompts are the files in prompts/; examples/ is the director's few-shot turn. Every model reply
is parsed, repaired where no judgement is needed (validator.normalize), and checked by the code
validator. A reply that fails is retried once with the problems appended; if it still fails the
caller gets a PlanError whose user_message is safe for the chat.

Acceptance check from the repository root (needs ANTHROPIC_API_KEY and AI_EDITOR_MODEL):

    python -m backend.editor.ai_edit.beats.service --window 27.12 71.78
"""
import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import llm, validator
from .llm import PlanError

LOG = logging.getLogger(__name__)
HERE = Path(__file__).parent
PROMPTS = HERE/'prompts'
EXAMPLES = HERE/'examples'
EXAMPLE_WINDOW = {'start': 27.12, 'end': 71.78}
CRITIC_ROUNDS = 2


@dataclass
class PlanResult:
    plan: dict
    issues: list = field(default_factory=list)          # validator issues of the final plan, as dicts
    notes: list = field(default_factory=list)           # deterministic repairs that were applied
    critic_score: float | None = None                   # the critic model's score (of the plan it last reviewed)
    validator_score: int = 100
    rounds: int = 0                                     # critic rounds run
    model: str = ''
    reply: str = ''                                     # revise: the chat reply
    changed_beat_ids: list = field(default_factory=list)


def prompt(name):
    return (PROMPTS/f'{name}_prompt.txt').read_text()


def window_words(transcript, window):
    if not window: return list(transcript)
    return [w for w in transcript if window['start']-1e-6 <= w['start'] < window['end']]


def _example():
    transcript = json.loads((EXAMPLES/'transcript_full.json').read_text())
    plan = json.loads((EXAMPLES/'edit_plan_example.json').read_text())
    return transcript, plan


def _director_input(transcript, window, instructions, source_video):
    return json.dumps({'source_video': source_video, 'window': window, 'user_instructions': instructions or None,
                       'transcript': window_words(transcript, window)})


def _check(plan, transcript, window=None):
    """(plan, notes, issues, blocking) for a candidate plan; blocking lists what must be fixed."""
    if not isinstance(plan, dict): return None, [], [], ['the plan is not a JSON object']
    if window: plan = {**plan, 'source_window': dict(window)}   # the window is the caller's, never the model's
    plan, notes = validator.normalize(plan, transcript)
    issues = validator.validate(plan, transcript)
    blocking = [f'rule {i.rule} beat {i.beat_id}: {i.problem}' for i in validator.high(issues)]
    return plan, notes, issues, blocking


def _ask(system, messages, accept):
    """Ask, accept(data) -> (value, blocking); retry once with the problems appended. Returns (value, blocking)."""
    text = llm.complete(system, messages)
    for attempt in (1, 2):
        try:
            value, blocking = accept(llm.parse_json(text))
        except ValueError as exc:
            value, blocking = None, [f'the reply was not valid JSON ({exc})']
        if not blocking or attempt == 2: return value, blocking
        LOG.info('AI editor reply rejected, retrying: %s', blocking[:5])
        messages = [*messages, {'role': 'assistant', 'content': text or '{}'},
                    {'role': 'user', 'content': 'The code validator rejected that answer:\n- ' + '\n- '.join(blocking[:40]) +
                     '\nFix every problem and return ONLY the corrected JSON, same schema, no commentary.'}]
        text = llm.complete(system, messages)


def make_plan(transcript, window=None, instructions=None, source_video='source.mp4', use_example=True):
    """Director, then up to two critic rounds. Raises PlanError if the plan still has high-severity issues."""
    if window: window = {'start': float(window['start']), 'end': float(window['end'])}
    messages = []
    if use_example:
        example_transcript, example_plan = _example()
        messages += [{'role': 'user', 'content': _director_input(example_transcript, EXAMPLE_WINDOW, None, example_plan['source_video'])},
                     {'role': 'assistant', 'content': json.dumps(example_plan)}]
    messages.append({'role': 'user', 'content': _director_input(transcript, window, instructions, source_video)})

    def accept(data):
        plan, notes, issues, blocking = _check(data, transcript, window)
        return (plan, notes, issues), blocking

    value, blocking = _ask(prompt('director'), messages, accept)
    if value is None or value[0] is None:
        raise PlanError('The AI editor could not make a plan for this clip. Try again.', '; '.join(blocking))
    plan, notes, issues = value
    plan.setdefault('source_video', source_video)
    result = PlanResult(plan=plan, notes=list(notes), model=llm.model())
    critic_system = prompt('critic')
    window = plan['source_window']
    for round_number in range(1, CRITIC_ROUNDS+1):
        result.rounds = round_number
        review = llm.complete(critic_system, [{'role': 'user', 'content': json.dumps({
            'transcript': window_words(transcript, window), 'plan': plan,
            'validator_issues': [i.as_dict() for i in issues]})}])
        try:
            data = llm.parse_json(review)
        except ValueError:
            LOG.info('critic reply was not JSON; keeping the plan'); break
        if isinstance(data.get('score'), (int, float)): result.critic_score = data['score']
        critic_issues = data.get('issues') or []
        fixed, fixed_notes, fixed_issues, fixed_blocking = _check(data.get('fixed_plan'), transcript, window)
        if fixed is not None and fixed.get('hook') and len(fixed_blocking) <= len(validator.high(issues)) and fixed != plan:
            plan, issues = fixed, fixed_issues
            result.notes += [n for n in fixed_notes if n not in result.notes]
        if not critic_issues and not validator.high(issues): break
    result.plan, result.issues = plan, [i.as_dict() for i in issues]
    result.validator_score = validator.score(issues)
    if validator.high(issues):
        raise PlanError('The AI editor could not make a plan that passes its checks. Try again.',
                        '; '.join(f'rule {i.rule} beat {i.beat_id}: {i.problem}' for i in validator.high(issues)))
    return result


def changed_beats(before, after):
    """Ids (in `after`) of beats that are new or differ in anything but their id."""
    strip = lambda b: json.dumps({k: v for k, v in b.items() if k != 'id'}, sort_keys=True)
    old = {strip(b) for b in before.get('beats', [])}
    return [b['id'] for b in after.get('beats', []) if strip(b) not in old]


def revise_plan(plan, transcript, message):
    """Apply one chat request to `plan`. Returns PlanResult with reply and changed_beat_ids; never changes the window."""
    window = plan['source_window']
    system = prompt('revise')
    messages = [{'role': 'user', 'content': json.dumps({'current_plan': plan, 'transcript': window_words(transcript, window),
                                                        'user_message': message})}]

    def accept(data):
        revised, notes, issues, blocking = _check(data.get('plan'), transcript, window)
        return (data, revised, notes, issues), blocking

    value, blocking = _ask(system, messages, accept)
    if blocking or value is None or value[1] is None:
        raise PlanError("I couldn't make that change in a way that passes the edit's checks, so the edit is unchanged. "
                        'Try rephrasing it.', '; '.join(blocking))
    data, revised, notes, issues = value
    changed = changed_beats(plan, revised)
    reply = str(data.get('reply') or '').strip()[:600] or ('Done.' if changed else 'No changes were needed.')
    return PlanResult(plan=revised, issues=[i.as_dict() for i in issues], notes=notes, validator_score=validator.score(issues),
                      model=llm.model(), reply=reply, changed_beat_ids=changed)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Make a beat plan from a word-level transcript and check it.')
    parser.add_argument('--transcript', default=str(EXAMPLES/'transcript_full.json'))
    parser.add_argument('--window', nargs=2, type=float, metavar=('START', 'END'))
    parser.add_argument('--instructions')
    parser.add_argument('--no-example', action='store_true', help='leave out the few-shot example (a fairer test on the example window itself)')
    parser.add_argument('--out', help='write the plan JSON here')
    args = parser.parse_args(argv)
    transcript = json.loads(Path(args.transcript).read_text())
    window = {'start': args.window[0], 'end': args.window[1]} if args.window else None
    try:
        result = make_plan(transcript, window, args.instructions, use_example=not args.no_example)
        plan, issues = result.plan, result.issues
    except PlanError as exc:
        print('PLAN FAILED:', exc.detail); return 1
    if args.out: Path(args.out).write_text(json.dumps(plan, indent=2))
    print(json.dumps({'model': result.model, 'critic_rounds': result.rounds, 'critic_score': result.critic_score,
                      'summary': validator.summary(plan, [validator.Issue(**i) for i in issues]),
                      'resemblance_to_example': validator.resemblance(plan, _example()[1]),
                      'repairs': result.notes, 'issues': issues}, indent=1))
    for beat in plan['beats']:
        print(f"{beat['id']:>3} {beat['start']:6.2f}-{beat['end']:6.2f} {beat['template']:<21} {beat.get('emphasis_text') or ''}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
