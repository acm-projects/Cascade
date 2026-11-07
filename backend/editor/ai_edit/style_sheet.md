# AI video editor: Scrapbook style sheet

Look: scrapbook

Claude edits video for the owner of this folder. Raw clips are in `Raw Footage/`, style references in `New References/` and `References/`, finished videos in `Exports/`, tools in `Tools/`.

This sheet replaced the "Point" sheet on 2026-11-06. The old sheet is kept, unused, as `CLAUDE.point-style (kept aside).md`. An instruction for one edit overrides this sheet for that edit only.

## The feel

A scrapbook that tells the story of what is being said. Everything looks made by hand and pinned to paper: cream paper with grain and torn edges, footage taped up like photos, handwritten words next to cut-out block labels, red marker circles, red tape. The picture always shows what the words say. Studied from: FireEdit (sketchbook frames, words around the speaker, red and black), the "Edited by Frazix" reel (paper cards, red labels, storyboard notes), the paper-and-tape podcast edits in `References/` (polaroid cut-outs, script words, maroon and cream), and "Animal B-roll level" (close, sharp, cinematic animal footage).

## Formats

- Podcasts, interviews and Q&A (talk): question first, then the answer, in that order, ending on the punchline. The speakers carry it; b-roll shows every concrete thing they name.
- B-roll films and nature clips: the footage carries it, a new shot every 1.5-3 s, handwritten lines as the narration.

## Picture

- Speaker shots: full frame, centred on whoever is talking, under the paper grain and torn top and bottom edges.
- Cutaways and b-roll: pinned up as a taped photo on paper (the frame shrinks to 80% with a white border, tilted about 2.5 degrees, tape on the top corners), alternating tilt left and right.
- B-roll shows exactly what is said, on the word or up to 0.2 s before it: "roar" means a lion or big cat roaring close up, "jaguar" means a jaguar, "Amazon" means aerial rainforest river. Animals are shown close and sharp (eyes, fur, mouths, slow push-ins), like "Animal B-roll level". Never stock of people or faces, never vague searches ("wildlife", "nature"). Name the animal or thing, then the action, then "close up" or "aerial".
- Podcasts: up to 6 b-roll shots per minute; 1.5-2.5 s each. If no shot truly shows it, stay on the speaker.
- Grade: warm and slightly faded, deep blacks, never a false tint.

## Words

- Captions word by word on the spoken frame, at most 5 words on screen, centred in the 52-72% height band.
- Small words are handwritten (Caveat, white). The one key word per phrase is a cut-out label in a bold block font, taking turns: cream paper with black text, red with white text, black with cream text, each a little tilted.
- The key word is always a real word (noun, verb, name or number), never filler (a, the, of, or, and, is, they're, it, that, so, to, in).
- Every fourth key word gets a red marker circle drawn around it.
- No full stops, no dots.
- One punchline at most, on a paper card in red marker caps, with the lead-in handwritten.

## Pacing and sound

- 25-40 cuts per minute where someone speaks, 35-55 in b-roll montage. Cuts and labels land on the beat; the voice is never moved to hit one.
- Sound: -14 LUFS, true peak at or below -1 dB, voice on top, music about 18-20 dB under it.

## Ending (every video, exactly like `New References/ENDWITHCASCADE.mov`)

1. One handwritten line on paper that sums the video up and makes it feel cool: a mood or a punchline, never a lesson or a call to action (e.g. "half pit bull, all sweetheart").
2. Then black, with only the wordmark "Cascade" in the centre: clean sans, filled with leopard print. It blurs in, holds, and leaves on a quick colour-split glitch. Nothing else on screen.

## Truth

- Every number shows a named source and year. No generated or staged footage passed off as real. Right animal, right place.
- Footage: the owner's own clips, public agency footage or free stock (Pexels), licence checked per clip. Never put footage from the reference folders into an export.

## Tools

- Caption burn-in needs `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`; the default `ffmpeg` lacks those filters.
- Whisper: `whisper-cli` with the model in `Tools/whisper-models/`.
