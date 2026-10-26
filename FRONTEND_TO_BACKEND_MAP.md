# Cascade: Frontend-to-Backend Traceability Matrix

## 1. Authentication & Pipeline (The Frog Journey)
* **Login/Signup Screen**: 
  * *Figma Action*: User enters credentials and clicks **Sign Up** / **Log In**.
  * *API Route*: `GET /login` / FastAPI auth endpoints.
  * *Database*: Stored in Neon SQL `users` table.
* **Pipeline Map (Lily Pads)**:
  * *Figma Action*: User selects a lily pad stage to jump through the workflow.
  * *API Route*: Fetches project pipeline status.

## 2. Video Processing & Upload
* **Main Video Drop**:
  * *Figma Action*: User drops a large video file into the project.
  * *API Route*: `POST /upload` (takes video, search query, mode, and clip_length)[cite: 5].
  * *Backend Action*: Kicks off processing job and returns a `job_id`.

## 3. Timeline & Editor Workspace
* **Job Tracking & Clip Retrieval**:
  * *Figma Action*: User views generated clips on the timeline tracks (Video, Subtitles, B-Roll, Audio).
  * *API Route*: `GET /jobs/{job_id}` to check status.
  * *API Route*: `GET /clips/{job_id}/{filename}` and `GET /api/my-clips` to fetch final clips for the editor[cite: 4, 6].