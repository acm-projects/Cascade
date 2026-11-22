# Music Library

Songs the AI Editor can cut to. Put songs you have the right to use here (sub-folders are fine).

**NCS (NoCopyrightSounds):** download tracks from https://ncs.io (free; each track page has a download
button). Keep the file name as NCS gives it, e.g. `Artist - Title [NCS Release].mp3`, so Cascade can read
the artist and title and write the credit line NCS asks for. Put the credit in your post caption.

The first time the editor runs after you add songs, Cascade measures each new song once (tempo, beats, the
drop, lyrics with Deepgram, mood tags with OpenAI) and caches the result in `.cascade/`. Remove a song by
deleting its file.

Song files and the `.cascade/` cache are not committed to git.
