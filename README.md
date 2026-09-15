<p align="center">
  <img src="https://media.tenor.com/xkZOIwwyF70AAAAM/frog-e1x.gif" alt="cascade-banner" />
</p>

<h1 align="center"> 🌊 Cascade </h1>

<div align="center"> 
  <strong>One video in. A full week of content out.</strong><br><br>
  Every creator has the same problem: you spend hours making one great video, and turning it into a TikTok, a tweet thread, and a LinkedIn post is another hour of work-- PER PLATFORM. Cascade is a web app that takes a single source video and, through real video processing, word-level speech-to-text, and multi-stage AI prompting, automatically produces a full week of platform-native content: a captioned short-form clip with AI-sourced b-roll, plus a Twitter/X thread, a LinkedIn post, an Instagram caption, and a TikTok/Reels script.
</div>

<br>

## MVP 🏆
* **Video Ingestion Pipeline:** Accepts an uploaded source video and extracts audio for processing.
* **Word-Level Transcription:** Speech-to-text with word-level timestamps, powering both captions and clip selection.
* **Multi-Stage AI Prompting:** Structured, validated LLM outputs that (1) select the best short-form moment, (2) write platform-native posts, and (3) generate a shot/caption plan.
* **Automated Clip Assembly:** FFmpeg-driven cutting, karaoke-style burned-in captions (ASS subtitle format), and AI-sourced b-roll compositing (Pexels API).
* **Platform Post Generation:** Auto-generated Twitter/X thread, LinkedIn post, Instagram caption, and TikTok/Reels script from the same source video.
* **Job Status Dashboard:** Async job pipeline (upload -> processing -> done) with live progress polling on the frontend.

## Stretch Goals 🌟
* **Multi-Clip Selection:** Detect and offer several strong candidate moments instead of just one.
* **Editable Output:** Let users tweak generated captions/posts before export instead of only copy-paste.
* **Style/Tone Presets:** Let users pick a voice (professional, funny, dramatic) that shifts all generated text together.
* **Direct Publishing:** OAuth into platforms and post directly instead of copy/paste.
* **YouTube Link Ingestion:** Accept a YouTube URL (via yt-dlp) as an alternative to a manual upload.

## Milestones 🎞️

<details closed>
<summary>  <strong> Week 1: The Setup 📁 </strong> </summary>
<br>
  
- **General:**
  - Decide team roles (Frontend vs Backend)
  - Set up GitHub repo, `.env` template, and API keys (transcription API, LLM, Pexels)
  - Everyone installs the stack and posts a working "Hello World" screenshot in the team chat (lol)
  - Read FFmpeg and yt-dlp docs now and familiarize yourself
- **Frontend:**
  - Finalize UI design and UX layout (Figma)
- **Backend:**
  - Make test requests to the transcription API and the LLM (confirm structured/JSON output works)

</details>

<details closed>
<summary>  <strong> Week 2: Hello World ⚡ </strong> </summary>
<br>
  
- **Frontend:**
  - Initialize React (Vite) + TypeScript + Tailwind project
  - Build basic layout: upload area, job status area, results area (stubbed)
- **Backend:**
  - Stand up FastAPI skeleton with an in-memory job dictionary
  - Build a fake background task that sleeps, updates progress a couple of times, then marks a job "done" with a fake result
  - Confirm the frontend can POST a job and poll `GET /jobs/{id}` through the fake stages end to end

</details>

<details closed>
<summary>  <strong> Week 3: Real Ingestion 🎬 </strong> </summary>
<br>
  
- **Backend:**
  - Replace the fake job with real video upload handling
  - Extract audio via FFmpeg/FFprobe (subprocess, explicit CLI flags)
  - Call the transcription API and store word-level timestamps
- **Frontend:**
  - Wire the upload form to the real endpoint
  - Show real (not fake) progress states as they come back

</details>

<details closed>
<summary>  <strong> Week 4: The Brain 🧠 </strong> </summary>
<br>
  
- **Backend:**
  - Prompt engineering: summarize the transcript into a brief
  - Multi-stage prompting with structured outputs: best-moment selection, social post generation, caption/shot plan
  - Add output validation (retry or flag malformed structured responses)
- **Frontend:**
  - Build UI components to display generated posts once available

</details>

<details closed>
<summary>  <strong> Week 5: The Cut 🎞️ </strong> </summary>
<br>
  
- **Backend:**
  - Cut the selected clip with FFmpeg based on the chosen timestamps
  - Burn in word-synced captions using ASS karaoke tags
  - Pull and composite b-roll from the Pexels Videos API
- **Frontend:**
  - Style the "generated clip" preview area (native HTML5 video player)

</details>

<details closed>
<summary>  <strong> Week 6: Full Loop 🔄 </strong> </summary>
<br>
  
- **Backend:**
  - Connect every stage (ingest -> transcribe -> prompt -> cut -> caption -> b-roll) into one real end-to-end pipeline
  - Return the finished video + all four platform posts from a single job
- **Frontend:**
  - Full integration: real upload -> real polling -> real results, no more stubs/fakes anywhere

</details>

<details closed>
<summary>  <strong> Week 7: Everything Works ✅ </strong> </summary>
<br>
  
- **All:**
  - Run the full pipeline against every test video the team has, back to back-- fix whatever breaks
  - NO NEW FUNCTIONALITY AFTER TONIGHT!!!!
  - Add timeouts/retries on every external API call, clear error messages (not generic "something went wrong"), transcript caching by file hash, and temp file cleanup after each job

</details>

<details closed>
<summary>  <strong> Week 8: Polish & Reliability + Presentation Creation ✨ </strong> </summary>
<br>
  
- **Frontend:** Polish fonts/colors/spacing, fix layout bugs, add a "How it Works" section
- **Backend:** Review API usage/quota limits, fix edge cases found in testing, final code review
- **All:** Confirm the demo path (specific test video -> known-good output) is bulletproof, WORK ON PRESENTATION!!!

</details>

<details closed>
<summary>  <strong> Week 9: Presentation Day Prep 🎬 </strong> </summary>
<br>
  
- Record a backup demo video in case live generation fails on stage
- Practice the pitch and live walkthrough, timed
- Freeze the repo--no last-minute changes the night before presentation

</details>

## Tech Stack 💻

<strong> IDE: </strong> VSCode                                                                        
<strong> Version Control: </strong> Git / GitHub                                                  
<strong> Design: </strong> Figma

<strong> Frontend </strong> 
- **Framework:** React (Vite) + TypeScript
- **Styling:** Tailwind CSS
- **State Management:** Zustand
- **Icons:** Lucide React
- **Playback:** Native HTML5 `<video>` element

<strong> Backend & AI </strong>  
- **Runtime/Framework:** Python + FastAPI
- **Async Jobs:** FastAPI BackgroundTasks + in-memory job dictionary
- **Validation:** Pydantic
- **Media Processing:** FFmpeg / FFprobe (subprocess, explicit CLI flags)
- **Captions:** ASS subtitle format with karaoke tags for word-synced highlighting
- **Transcription:** Hosted speech-to-text API with word-level timestamp granularity
- **LLM:** OpenAI or Google Gemini (Flash)-- structured outputs, multi-stage prompting
- **Stock Footage:** Pexels Videos API (free tier: 200 req/hour, 20,000/month)
- **Storage:** Local filesystem (S3 if time allows)

<strong> Deployment </strong>
- Local for the demo
- If hosted: a container-based host that supports long-running processes and FFmpeg (Render, Railway, Fly.io)-- not Vercel/Netlify, which time out before a render finishes and don't ship FFmpeg

## Helpful Resources 🔎

<strong> Frontend: </strong>
- [React Documentation](https://react.dev/learn)
- [Vite Guide](https://vitejs.dev/guide/)
- [Tailwind CSS Docs](https://tailwindcss.com/docs)
- [Zustand State Management](https://docs.pmnd.rs/zustand/getting-started/introduction)
- 🎥 [React + Vite + TypeScript + Tailwind Crash Course (YouTube)](https://www.youtube.com/watch?v=siTUv1L9ymM)
- 🎥 [Tailwind CSS Full Course 2026 (YouTube)](https://www.youtube.com/watch?v=6biMWgD6_JY)
- 🎥 [Tailwind CSS Crash Course, Traversy Media (YouTube)](https://www.youtube.com/watch?v=UBOj6rqRUME)
- 🎥 [Zustand Beginner Tutorial (YouTube)](https://www.youtube.com/watch?v=gz4NgSWjHoY)
- 🎥 [5 Zustand Best Practices in 5 Minutes (YouTube)](https://www.youtube.com/watch?v=6tEQ1nJZ51w)

<strong> Backend: </strong>
- [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/)
- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [Pydantic Docs](https://docs.pydantic.dev/latest/)
- 🎥 [FastAPI Full Crash Course (YouTube, freeCodeCamp)](https://www.youtube.com/watch?v=tLKKmouUams)
- 🎥 [FastAPI Full Crash Course, Python's Fastest Web Framework (YouTube)](https://www.youtube.com/watch?v=rvFsGRvj9jo)
- 🎥 [Python Pydantic Tutorial: Complete Data Validation Course, Corey Schafer (YouTube)](https://www.youtube.com/watch?v=M81pfi64eeM)

<strong> Media Processing: </strong>
- [FFmpeg Documentation](https://ffmpeg.org/ffmpeg.html)
- [FFmpeg Filters](https://ffmpeg.org/ffmpeg-filters.html)
- [FFmpeg Wiki](https://trac.ffmpeg.org/wiki)
- [ASS Subtitle Tags (karaoke/word highlighting)](https://aegisub.org/docs/latest/ass_tags/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- 🎥 [FFmpeg Tutorial for Beginners: Mastering the Command Line (YouTube)](https://www.youtube.com/watch?v=4SduPbaX77Y)
- 📝 [Burning ASS Subtitles with FFmpeg — subtitles filter reference (written guide)](https://www.ffmpeg-micro.com/blog/ffmpeg-subtitles-filter-guide)
- 📝 [How to Add Subtitles to a Video with FFmpeg, incl. ASS format (written guide, Bannerbear)](https://www.bannerbear.com/blog/how-to-add-subtitles-to-a-video-file-using-ffmpeg/)

<strong> AI & APIs: </strong>
- [OpenAI Speech-to-Text](https://platform.openai.com/docs/guides/speech-to-text)
- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [Google Gemini API Docs](https://ai.google.dev/gemini-api/docs)
- [Pexels API Documentation](https://www.pexels.com/api/documentation/)
- 🎥 [OpenAI Structured Output Tutorial (YouTube)](https://www.youtube.com/watch?v=eJvYafgLh40)
- 🎥 [Gemini API with Python — Getting Started (YouTube)](https://www.youtube.com/watch?v=qfWpPEgea2A)

<strong> Software to Install: </strong>
- [VSCode](https://code.visualstudio.com/download)
- [Git](https://git-scm.com/downloads)
- [Node.js](https://nodejs.org/en/download)
- [Python 3.11+](https://www.python.org/downloads/)
- [FFmpeg](https://ffmpeg.org/download.html)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (`pip install -U yt-dlp`)
- [Postman](https://www.postman.com/downloads/)
- [Figma](https://www.figma.com/downloads/)

## Developers 🐸

- Abhishri Dave
- Fawaz Jamshed
- Kashmine Zadia Shaik
- Manila Cholleti
- Sai Varun Mallela

**Project Manager:** Mohammad Mehrab  
**Industry Mentor:** Jackson Parrish
