# Working on Cascade Cinema (notes for any coding model or person)

This folder is the AI Editor's finished-edit engine. Read `docs/cinema-editor.md` first; it has the map.

- The engine is deterministic and model-free. Never make `engine.py`, `render.py`, `speech.py`, `score.py`, `stamp.py`, `look.py` call an AI model.
- AI is used in exactly one place: `planner.py`, which turns a transcript and frames into a `CinemaPlan` (`plan.py`). Any model may fill that role. Do not name a specific model in code or prompts; the model is configuration (`CASCADE_EDIT_MODEL`).
- Creative direction lives in `STYLE_GUIDE.md` (prose), `prompts/director.md` (what the planner is told) and `style.json` (numbers). Change those before changing code.
- A saved edit is `project.json` (`project.py`). Keep it loadable: if you change `CinemaPlan`, give new fields defaults and keep old projects opening (there is a test).
- Simple follow-ups are handled without AI in `revise.py`. Add a rule there when a request is a switch or a mechanical timeline change.
- Run `python -m pytest tests/application/test_cinema.py tests/application/test_ai_edit.py` before committing. The tests run with every AI planner switched off.
- To judge a render, make a contact sheet (`ffmpeg -i edited.mp4 -vf "fps=1,scale=300:-2,tile=10x6" sheet.jpg`) and look at it; check loudness with `ffmpeg -i edited.mp4 -af ebur128 -f null -`.
