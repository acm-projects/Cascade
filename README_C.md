# Cascade Visual Prototype

## Files

Keep these files in the same folder:

- index.html — Landing page
- login.html — Demo sign-in page
- projects.html — Projects dashboard
- canvas.html — Branching discovery canvas
- editor.html — Editing workspace
- exports.html — Finished clips and exports
- styles.css — Shared styling
- app.js — Page content and interactions
- README.md — These instructions

## Open the website

Open index.html in your browser.

For more consistent saving between pages, open a terminal
inside this folder and run:

python3 -m http.server 8080

Then open:

http://localhost:8080

## Try the complete flow

1. Click Get started.
2. Click Enter demo without signing in.
3. Open Conversations by the waterfall.
4. Explore the canvas. Click Fit to see all branches.
5. Select clips and click Continue to editor.
6. Try the Chat, Captions, Aspect ratio, and B-roll tabs.
7. Click Save finished clip.
8. Open Exports and simulate an export.
9. Click Edit again to return to editing.

## Demo behavior

Authentication, AI discovery, research, B-roll generation,
video editing, and exports are simulated.

The previews use illustrations rather than actual footage.
Choosing a video saves its filename, not the video itself.

Project data, editing settings, chat history, and saved versions
are stored locally in your browser.

Demo downloads contain editing settings and optional sample
captions, not rendered video.

Use Reset demo in the account menu to restore the sample data.

## Existing Cascade app

Keep this prototype in a separate folder from your working
FastAPI app.

This prototype is not connected to Clerk, Neon, S3, Ollama,
or your existing API endpoints.