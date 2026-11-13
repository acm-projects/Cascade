# Cascade Cinema: the editing guide

This is Cascade's own editing style, distilled from the INSPO library (`INSPO_NOTES.md`). It is the
single place the creative direction is written down. Three files apply it:

| What | Where | Who reads it |
|---|---|---|
| Story and taste (what to keep, where moments go) | `prompts/director.md` | the AI planner, whichever model |
| Numbers (pause length, caption size, colours, levels) | `style.json` | the engine, at start-up |
| Craft (how a cut, caption, grade, mix is made) | the Python modules | nobody at run time: it is code |

## 1. Dialogue comes first
- Lock the words before anything else. Cut on word boundaries moved to where the voice's energy really starts and stops; never inside a word.
- Remove ums, stutters, "you know"/"I mean" asides and false starts. Keep repetition said on purpose ("stealing, stealing, stealing").
- No pause longer than 0.16 s inside a line. Every join gets a 12 ms equal-power crossfade.
- One voice at a time. The asker's interjections inside an answer go.

## 2. Every edit is a story with a lesson
- Cold open on the strongest line in the clip, wherever it is said. Then the question, whole. Then the answer rebuilt in story order. Then the payoff.
- The music stops dead just before the payoff; a low hit lands on its first word.
- After the last word, one closing message on its own over the most beautiful footage: what the story asks of the viewer. For nature and climate clips it speaks to the kids who come next.
- 35-60 s of speech. Cut lines before running long. Never change what the speaker meant.

## 3. Picture
- Original aspect by default. A reel (9:16) only when asked; then speakers are re-centred on their faces and captions move below.
- The picture changes every 2-4 s: b-roll, a punch-in, or a designed moment.
- B-roll fills the frame, arrives 0.12 s before its word, holds 1.5-3.4 s, and shows the concrete thing being named. Aim for 40-60% of the runtime. Stay on the speaker for the emotional lines.
- Only call footage "the Amazon" when the clip was searched for by that name.
- Designed moments, at least 6 s apart: a giant word behind the speaker, an outline word, a coloured rim of light, one full-screen slam at most.
- Grade: rich blacks, teal shadows, warm skin; "forest" lifts greens. Black-and-white for loss.

## 4. Type
- One family: Inter Tight, heavy and tight. Captions sit in the empty side of the frame (16:9) or low centre (9:16).
- A caption block builds word by word and stays up until the next block replaces it. It never blinks off mid-thought.
- One keyword per block on a coloured chip. Colour means something: blue water, green life, mint hope, red danger, gold money, amber Earth.
- Expressive text (giant words, the slam, the payoff, the message) is separate from captions and hides them while it is up.

## 5. Sound
- Voice on top, always. Music 17 dB under speech and ducked further while someone talks. Master to -14 LUFS, -1.2 dB true peak.
- The score is composed per edit (felt piano, pad, sub) in a mood the planner picks. No stock "whoosh/ding" packs.
- The music resolves before the sign-off.

## 6. The Cascade sign-off
A wet blue paint stroke sweeps across the dark, flicks water off its end, and "Cascade" is brushed over it. 2.5 s. Only the brush and the splash are heard.
