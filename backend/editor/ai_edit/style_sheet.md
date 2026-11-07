# AI video editor

Claude edits video for the owner of this folder. Raw clips are in `Raw Footage/`, style references in `References/`, finished videos in `Exports/`, tools in `Tools/`.

## Brand sheet: required on every edit

`Brand/brand-sheet.html` ("The Point") was approved on 2026-11-05, replacing the 2026-11-04 version (saved as `Brand/brand-sheet-v1-approved-2026-11-04.html`). Read it before editing and follow it on every edit. Depart from it only when the owner asks. An instruction for one edit overrides the sheet for that edit only.

Format (owner's choice, 2026-11-05): follow `Exports/heat-cook-the-planet-reel.mp4`, real people in their own voices over real footage. Do not follow `Exports/still-home-reel.mp4`, AI narration and very short lines.

Core rules:
- Colour: Point Blue #3D4EFF, Ink #0C0D13, Bone #EDEEE8. Flare #FF6A3D for losses and warnings only. Blue is for shapes; words stay Bone. No gradients.
- Fonts: Bricolage Grotesque ExtraBold condensed (hero), Instrument Sans SemiBold (connecting words, 50 px), Instrument Serif Italic (once per video at most).
- Captions: word by word on the spoken frame, one hero word per phrase, no full stops and no dots (only a verdict's last word gets the dot), 5 words on screen at most, centred in the 52-72% height band, clear of the right 14%, bottom 20% and top 9%.
- Ending: the End card shows up to 3 hero words and ONE line that sums the video up and makes it feel cool (a mood or a punchline, never a lesson or a call to action), with "Edited by Cascade" under it.
- Pacing: 25-40 cuts per minute, a visual change every 1.5-3 s, graphics on 30-40% of runtime. Zooms are instant jumps between Wide 100%, Mid 115%, Close 130%.
- Graphics: Dot transition (topic changes only, 4 per minute at most), Point field (one every 15 s at most), Point window, Tally, Numbers, End card. Fast start, soft landing, 4-12 frames.
- Sound: -14 LUFS, true peak at or below -1 dB, voice on top, one licensed music track about 20 dB under the voice.
- Never copy the references' signatures, and never put footage from `References/` into an export unless the owner confirms they have the rights.

B-roll (every video):
- When a speaker names a place, person, event, thing or number, makes a claim, or describes something hard to picture, show it. Also after 5 s of unchanged speaker, or to cover a cut.
- 1-3 s per shot, arriving on the key word or up to 0.2 s ahead. Voice keeps running, captions stay on top. Speaker-led videos are 40-60% off the speaker, b-roll and graphics together.
- No filler: if no shot truly matches, use a graphic or stay on the speaker. Stay on the face for emotional lines and the deliberate stillness.
- Source: the owner's clips first, then public agency footage and free stock, with the licence checked per clip.

Edits from the references (own versions, in `Brand/brand-sheet.html`; used when content calls for them): Backdrop swap, Number over footage, Proof run, Evidence card, Footage through the dot, Band opening; Earth mode only: Data map, Bright reset, Bookend.

Music sync (every video):
- Cut voice and picture first, then compose the track to fit. With a licensed track, cut the picture to its beats.
- Montage: 80%+ of cuts on a beat, within 2 frames. One tempo per video, changing only between story parts.
- Effects and graphics land on beats. Tuned effects match the track's key. Swell ends on the beat its Dot transition lands.
- The voice wins: never move a spoken word to hit a beat, captions stay on the spoken frame, and effects never cover a stressed word.
- Report the share of cuts and effects on a beat after every edit. Claude can't listen, so the owner judges the feel.

Earth mode (every climate, environment and nature video; wins over Core where they differ):
- The dot is the planet: blue in Home and What's left, Flare in Loss and Cost, changing on a hard cut. No new colours. Flare may run through Loss and Cost.
- Story: Home about 25%, Loss 35%, Cost 20%, What's left 20%. End on one action for the viewer.
- Footage full frame on 60-80% of runtime, graphics on 15-25%, speaker optional. Grade with deeper shadows and real colour, never a false tint. A flat Ink dim of up to 30% may sit behind captions.
- Pacing: 35-55 cuts per minute in montage, 25-40 where someone speaks. One hold of up to 8 s. Up to 3 planned silences of 0.5-1.2 s. Lines of 3-6 words, voiceover at 80-120 wpm. A pause limit given for one edit still wins.
- Graphics: Toll (Tally in Flare, 5 lines at most), Closing (circle of footage shrinks to a Flare dot, once per video), Verdict card (caps on Ink, 2 per video at most, no music under the line), Sourced number, Earth word (footage through a word, once per video), Cinema band (wide footage on Ink), End card with one action.
- Sound: music about 14-16 dB under the voice, dark and low, level swing 8-12 LU on dramatic films, final mix still -14 LUFS and -1 dB peak. Real ambience under everything. Silence before a Verdict.
- Truth: every number shows a named source and year, checked when used. No generated or staged footage passed off as real. Right place, right event. Dead or suffering animals 1 s at most, no gore.
- Footage: the owner's own, public agency footage or free stock, with the licence checked per clip.

## Tools

- Caption burn-in needs `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`; the default `ffmpeg` lacks those filters.
- Whisper: `whisper-cli` with the model in `Tools/whisper-models/`.
