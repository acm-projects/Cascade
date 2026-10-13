/*
  Cascade: existing Clerk + FastAPI pipeline.

  One video + one prompt -> one generated clip.

  Used by the updated:
  login_C.html
  projects_C.html
  canvas_C.html
  editor_C.html
  exports_C.html
*/

(() => {
  const $ = id => document.getElementById(id);

  const page = document.body.dataset.page;

  const LOGIN_URL = new URL(
    "login_C.html",
    window.location.href
  ).href;

  let project = null;
  let selectedIndex = 0;
  const query = new URLSearchParams(location.search);
  let userId = null;
  let sourceURL = null;
  let restoredSource = null;
  let processing = false;
  let signedOut = false;

  const mediaURLs = [];

  function setStatus(message) {
    const status = $("status");

    if (status) {
      status.textContent = message;
    }
  }

  function wait(milliseconds) {
    return new Promise(resolve => {
      setTimeout(resolve, milliseconds);
    });
  }

  function loadScript(url, publishableKey) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");

      script.src = url;
      script.crossOrigin = "anonymous";

      if (publishableKey) {
        script.setAttribute(
          "data-clerk-publishable-key",
          publishableKey
        );
      }

      script.onload = resolve;

      script.onerror = () => {
        reject(new Error("Could not load Clerk."));
      };

      document.head.appendChild(script);
    });
  }

  function redirectToLogin() {
    signedOut = true;

    if ($("protected-page")) {
      $("protected-page").hidden = true;
    }

    if ($("account")) {
      $("account").hidden = true;
    }

    window.location.replace(LOGIN_URL);
  }

  // Every protected backend request gets the real
  // Clerk session token. app1.py verifies that token.
  async function apiFetch(url, options = {}) {
    if (signedOut) {
      throw new Error("Please sign in again.");
    }

    const token =
      await window.Clerk.session?.getToken();

    if (!token) {
      redirectToLogin();

      throw new Error("Please sign in again.");
    }

    const headers = new Headers(
      options.headers || {}
    );

    headers.set(
      "Authorization",
      "Bearer " + token
    );

    const response = await fetch(url, {
      ...options,
      headers,
      cache: "no-store"
    });

    if (!response.ok) {
      let message =
        "Request failed (HTTP " +
        response.status +
        ").";

      try {
        const error = await response.json();

        if (typeof error.detail === "string") {
          message = error.detail;
        }
      } catch {
        // Keep the HTTP message if no JSON was returned.
      }

      if (response.status === 401) {
        redirectToLogin();
      }

      throw new Error(message);
    }

    return response;
  }

  async function apiJSON(url, options) {
    const response = await apiFetch(
      url,
      options
    );

    return response.json();
  }

  // Scope saved prototype references to the real user.
  function jobStorageKey() {
    return "cascade-one-clip-job:" + userId + ":" + project?.id;
  }

  function projectStorageKey() {
    return "cascade-simple-project:" + userId;
  }

  function getSavedJob() {
    try {
      return sessionStorage.getItem(
        jobStorageKey()
      );
    } catch {
      return null;
    }
  }

  function saveJob(jobId) {
    try {
      sessionStorage.setItem(
        jobStorageKey(),
        jobId
      );
    } catch {
      // The editor link also carries the job ID.
    }
  }

  function getProjectName() { return project?.name || "Untitled project"; }

  function projectURL(page, job, index = 0) {
    const params = new URLSearchParams({project: project.id});
    if (job) { params.set("job", job); params.set("clip", index); }
    return page + "?" + params;
  }

  async function loadProject() {
    const id = query.get("project");
    if (!id) throw new Error("Choose a project from the projects page first.");
    project = await apiJSON("/api/projects/" + encodeURIComponent(id));
    document.querySelectorAll('a[href="canvas_C.html"], a[href="editor_C.html"], a[href="exports_C.html"]')
      .forEach(link => { link.href = projectURL(link.getAttribute("href"), query.get("job"), Number(query.get("clip") || 0)); });
  }

  async function downloadClip(clip, captions = false) {
    const response = await apiFetch(captions ? clip.captions_url : clip.clip_url);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url; link.download = captions ? "captions.vtt" : "cascade-clip.mp4";
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function waitFeature(jobId) {
    while (!signedOut) {
      const job = await apiJSON("/api/features/" + jobId);
      if (job.state === "error") throw new Error(job.message);
      if (job.state === "done") return job;
      setStatus(job.message); await wait(1500);
    }
    throw new Error("Please sign in again.");
  }

  function showAccount() {
    const user = window.Clerk.user;
    const profile = document.createElement("button");
    profile.type = "button"; profile.textContent = "Profile";
    profile.onclick = () => window.Clerk.openUserProfile();
    $("account")?.appendChild(profile);

    const name =
      user.fullName ||
      user.username ||
      user.primaryEmailAddress?.emailAddress ||
      "Your account";

    if ($("account-name")) {
      $("account-name").textContent = name;
    }

    if ($("account-id")) {
      $("account-id").textContent =
        "Account ID: " + userId;
    }

    if ($("account")) {
      $("account").hidden = false;
    }

    if ($("sign-out")) {
      $("sign-out").onclick = async () => {
        const button = $("sign-out");

        button.disabled = true;

        try {
          await window.Clerk.signOut({
            redirectUrl: LOGIN_URL
          });
        } catch (error) {
          setStatus(
            error.message ||
            "Could not sign out. Try again."
          );

          button.disabled = false;
        }
      };
    }
  }

  // A video element cannot add an Authorization header.
  // Fetch the protected video first, then play its Blob URL.
  async function attachClip(video, clip) {
    const clipURL = new URL(
      clip.clip_url,
      window.location.origin
    );

    if (
      clipURL.origin !== window.location.origin ||
      !clipURL.pathname.startsWith("/clips/")
    ) {
      throw new Error(
        "The server returned an invalid clip URL."
      );
    }

    const response = await apiFetch(
      clipURL.href
    );

    const videoBlob = await response.blob();

    const videoURL = URL.createObjectURL(
      videoBlob
    );

    mediaURLs.push(videoURL);

    video.src = videoURL;

    if (clip.captions_url) {
      try {
        const captionsURL = new URL(
          clip.captions_url,
          window.location.origin
        );

        if (
          captionsURL.origin !== window.location.origin ||
          !captionsURL.pathname.startsWith("/clips/")
        ) {
          throw new Error(
            "Invalid captions URL."
          );
        }

        const captionsResponse = await apiFetch(
          captionsURL.href
        );

        const captionsText =
          await captionsResponse.text();

        const captionsBlob = new Blob(
          [captionsText],
          {
            type: "text/vtt"
          }
        );

        const captionsBlobURL =
          URL.createObjectURL(captionsBlob);

        mediaURLs.push(captionsBlobURL);

        const track =
          document.createElement("track");

        track.kind = "captions";
        track.label = "Speech captions";
        track.srclang = "en";
        track.src = captionsBlobURL;
        track.default = true;

        video.appendChild(track);
      } catch (error) {
        setStatus(
          "Clip ready. Captions could not load: " +
          error.message
        );
      }
    }

    video.hidden = false;
  }

  async function showCanvasClip(jobId, job) {
    const group = document.querySelector(".clip-group");
    group.replaceChildren();
    selectedIndex = 0;
    for (const [index, clip] of (job.clips || []).entries()) {
      const card = document.createElement("article"); card.className = "clip-placeholder";
      const label = document.createElement("label");
      const select = document.createElement("input"); select.type = "radio"; select.name = "selected-clip"; select.checked = index === 0;
      select.onchange = () => { selectedIndex = index; $("open-editor").href = projectURL("editor_C.html", jobId, index); };
      label.append(select, document.createTextNode(" Select clip " + (index + 1)));
      const title = document.createElement("h3"); title.textContent = clip.title || "Generated clip";
      const detail = document.createElement("p"); detail.className = "muted";
      detail.textContent = Number(clip.start).toFixed(1) + "–" + Number(clip.end).toFixed(1) + "s · " + (clip.explanation || "");
      const video = document.createElement("video"); video.controls = true; video.playsInline = true;
      card.append(label, video, title, detail); group.appendChild(card);
      await attachClip(video, clip);
    }
    const link = $("open-editor"); link.href = projectURL("editor_C.html", jobId, 0);
    link.classList.remove("disabled-link"); link.removeAttribute("aria-disabled"); link.onclick = null;
  }

  async function pollJob(jobId) {
    while (!signedOut) {
      const job = await apiJSON(
        "/api/features/" + encodeURIComponent(jobId)
      );

      if (job.state === "error") {
        throw new Error(
          job.message ||
          "Video processing failed."
        );
      }

      if (job.state === "done") {
        if (signedOut) return;

        if (job.clips?.length) {
          setStatus(job.clips.length + " clip(s) ready.");

          await showCanvasClip(
            jobId,
            job
          );
        } else {
          setStatus(
            "No matching clip was found. Try a different prompt."
          );
        }

        return;
      }

      setStatus(
        job.message ||
        "Processing video…"
      );

      await wait(1500);
    }
  }

  function resetClipCard() {
    document.querySelector(".clip-group").replaceChildren();
    $("open-editor").classList.add("disabled-link");
    $("open-editor").setAttribute("aria-disabled", "true");
    $("open-editor").onclick = event => event.preventDefault();
  }

  // Projects are persisted by the backend and scoped to the verified Clerk user.
  async function initializeProjects() {
    const data = await apiJSON("/api/projects");
    const tiles = $("project-tiles");
    if (!data.projects.length) tiles.textContent = "No saved projects yet.";
    data.projects.forEach(item => {
      const tile = document.createElement("a"); tile.className = "button project-tile";
      tile.textContent = item.name; tile.href = "canvas_C.html?project=" + item.id;
      tiles.appendChild(tile);
    });
    const library = await apiJSON("/api/my-clips");
    for (const clip of library.clips) {
      const button = document.createElement("button"); button.type = "button";
      button.textContent = "Download · " + (clip.title || "Previously generated clip");
      button.onclick = () => downloadClip(clip).catch(error => setStatus(error.message));
      $("clip-library").appendChild(button);
    }
    if (!library.clips.length) $("clip-library").textContent = "No previously generated clips.";
    $("project-form").onsubmit = async event => {
      event.preventDefault(); const button = event.submitter; button.disabled = true;
      try {
        const item = await apiJSON("/api/projects", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name: $("project-name").value.trim()})});
        location.href = "canvas_C.html?project=" + item.id;
      } catch (error) { setStatus(error.message); button.disabled = false; }
    };
  }

  // Canvas page
  async function initializeCanvas() {
    $("project-title").textContent =
      getProjectName();

    $("open-editor").onclick = event => {
      event.preventDefault();

      setStatus(
        "Generate Clip 1 first, then open the editor."
      );
    };

    $("source-video").onchange = () => {
      restoredSource = null;
      const file =
        $("source-video").files[0];

      $("file-name").textContent =
        file?.name ||
        "No video selected";

      if (sourceURL) {
        URL.revokeObjectURL(sourceURL);
      }

      if (file) {
        sourceURL =
          URL.createObjectURL(file);

        $("source-player").src =
          sourceURL;

        $("source-player").hidden = false;

        $("source-empty").hidden = true;
      } else {
        $("source-player")
          .removeAttribute("src");

        $("source-player").hidden = true;

        $("source-empty").hidden = false;
      }
    };

    $("generate-clip").onclick = async () => {
      if (processing) return;

      const file =
        $("source-video").files[0] || restoredSource;

      const prompt =
        $("clip-prompt").value.trim();

      if (!file) {
        setStatus("Choose a video first.");
        return;
      }

      if (!prompt) {
        setStatus(
          "Enter the moment you want to find."
        );
        return;
      }

      processing = true;

      $("generate-clip").disabled = true;
      $("source-video").disabled = true;
      $("clip-prompt").disabled = true;

      try {
        const formData = new FormData();

        formData.append("project_id", project.id);
        formData.append("engine", $("search-engine").value);
        formData.append(
          "video",
          file
        );

        formData.append(
          "search",
          prompt
        );

        formData.append(
          "mode",
          "both"
        );

        formData.append(
          "clip_length",
          "30"
        );

        setStatus("Uploading video…");

        const upload = await apiJSON(
          "/upload",
          {
            method: "POST",
            body: formData
          }
        );

        if (!upload.job_id) {
          throw new Error(
            "The server did not return a job ID."
          );
        }

        saveJob(upload.job_id);
        const option = document.createElement("option"); option.value = upload.job_id; option.textContent = prompt + " · " + file.name;
        $("job-history").prepend(option); $("job-history").value = upload.job_id;

        resetClipCard();

        await pollJob(
          upload.job_id
        );
      } catch (error) {
        setStatus(
          error.message ||
          "Could not create the clip."
        );
      } finally {
        processing = false;

        $("generate-clip").disabled = false;
        $("source-video").disabled = false;
        $("clip-prompt").disabled = false;
      }
    };

    // Restore the most recent job when returning
    // from the editor within this browser tab.
    const history = $("job-history");
    project.jobs.filter(job => job.kind !== "research").forEach(job => {
      const option = document.createElement("option"); option.value = job.job_id;
      option.textContent = (job.kind === "caption-styles" ? "Caption styles" : job.prompt || "Upload") + " · " + job.source_name;
      history.appendChild(option);
    });
    history.onchange = async () => {
      if (!history.value || processing) return;
      processing = true; $("generate-clip").disabled = true; resetClipCard();
      try { saveJob(history.value); await pollJob(history.value); }
      catch (error) { setStatus(error.message); }
      finally { processing = false; $("generate-clip").disabled = false; }
    };
    const jobId = query.get("job") || getSavedJob() || project.jobs.find(job => job.kind !== "research")?.job_id;
    const original = project.jobs.find(job => job.kind === "generation");
    if (original) {
      try {
        const response = await apiFetch("/api/projects/" + project.id + "/source/" + original.job_id);
        restoredSource = new File([await response.blob()], original.source_name || "video.mp4");
        sourceURL = URL.createObjectURL(restoredSource);
        $("source-player").src = sourceURL; $("source-player").hidden = false; $("source-empty").hidden = true;
        $("file-name").textContent = restoredSource.name + " (saved upload)";
        $("clip-prompt").value = original.prompt;
      } catch (error) { setStatus(error.message); }
    }

    if (jobId) {
      if (!project.jobs.some(item => item.job_id === jobId)) throw new Error("This generation does not belong to the selected project.");
      processing = true;

      $("generate-clip").disabled = true;

      try {
        await pollJob(jobId);
      } catch (error) {
        setStatus(error.message);
      } finally {
        processing = false;

        $("generate-clip").disabled = false;
      }
    }
  }

  // Editor page
  async function initializeEditor() {
    $("project-title").textContent =
      getProjectName();

    document.querySelectorAll("[data-tab]")
      .forEach(button => {
        button.onclick = () => {
          const active =
            button.dataset.tab;

          document.querySelectorAll("[data-tab]")
            .forEach(tab => {
              const selected =
                tab.dataset.tab === active;

              tab.classList.toggle(
                "active",
                selected
              );

              tab.setAttribute(
                "aria-selected",
                String(selected)
              );
            });

          document.querySelectorAll(".tab-panel")
            .forEach(panel => {
              panel.hidden =
                panel.id !== active + "-panel";
            });
        };
      });

    const query =
      new URLSearchParams(
        window.location.search
      );

    const jobId =
      query.get("job") ||
      getSavedJob();

    if (!jobId) {
      setStatus(
        "No generated clip selected. Go back to the canvas and generate Clip 1."
      );

      return;
    }

    if (!project.jobs.some(item => item.job_id === jobId)) throw new Error("This generation does not belong to the selected project.");

    // FastAPI verifies that this user owns the job.
    const job = await apiJSON(
      "/api/features/" + encodeURIComponent(jobId)
    );

    if (
      job.state !== "done" ||
      !job.clips?.[0]
    ) {
      setStatus(
        job.message ||
        "This clip is not ready. Go back to the canvas."
      );

      return;
    }

    saveJob(jobId);

    selectedIndex = Number(query.get("clip") || 0);
    const clip = job.clips[selectedIndex];
    if (!clip) throw new Error("Selected clip not found.");
    document.querySelectorAll('a[href^="exports_C.html"]').forEach(link => { link.href = projectURL("exports_C.html", jobId, selectedIndex); });

    $("editor-clip-title").textContent =
      "Clip " + (selectedIndex + 1) + " · " +
      (clip.title || "Generated clip");

    await attachClip(
      $("editor-video"),
      clip
    );

    $("editor-empty").hidden = true;

    $("timeline-end").textContent =
      Math.round(
        Number(clip.end) -
        Number(clip.start)
      ) + "s";

    document.querySelector(".mini-branches").replaceChildren();
    job.clips.forEach((item, index) => {
      const link = document.createElement("a"); link.className = "mini-clip" + (index === selectedIndex ? " active" : "");
      link.textContent = "Clip " + (index + 1); link.href = projectURL("editor_C.html", jobId, index);
      document.querySelector(".mini-branches").appendChild(link);
    });
    $("save-clip").onclick = async () => {
      try {
        await apiJSON("/api/projects/" + project.id + "/saved-clips", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job_id: jobId, clip_index: selectedIndex})});
        setStatus("Clip saved to this project. Find it on Exports.");
      } catch (error) { setStatus(error.message); }
    };
    $("caption-styles").onclick = async () => {
      const button = $("caption-styles"); button.disabled = true;
      try {
        const response = await apiJSON("/api/projects/" + project.id + "/caption-styles", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job_id: jobId, clip_index: selectedIndex})});
        await waitFeature(response.job_id);
        location.href = projectURL("canvas_C.html", response.job_id);
      } catch (error) { setStatus(error.message); button.disabled = false; }
    };
    $("research-form").onsubmit = async event => {
      event.preventDefault(); const button = event.submitter; button.disabled = true;
      try {
        const response = await apiJSON("/api/projects/" + project.id + "/research", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job_id: jobId, topic: $("research-topic").value.trim()})});
        const result = await waitFeature(response.job_id);
        $("research-result").textContent = JSON.stringify(result.research, null, 2);
        setStatus("Research complete.");
      } catch (error) { setStatus(error.message); } finally { button.disabled = false; }
    };
    const researchJob = project.jobs.find(item => item.kind === "research");
    if (researchJob) {
      const result = await apiJSON("/api/features/" + researchJob.job_id);
      if (result.research) $("research-result").textContent = JSON.stringify(result.research, null, 2);
    }
    setStatus("Selected clip loaded. Save, download, caption styles, and research are connected. Other editing controls remain unfinished.");
  }

  async function initializeExports() {
    const list = $("saved-clips"); list.replaceChildren();
    const entries = [...project.saved_clips];
    if (query.get("job")) entries.unshift({job_id: query.get("job"), clip_index: Number(query.get("clip") || 0)});
    const seen = new Set();
    for (const entry of entries) {
      const key = entry.job_id + ":" + entry.clip_index; if (seen.has(key)) continue; seen.add(key);
      if (!project.jobs.some(item => item.job_id === entry.job_id)) { setStatus("This clip does not belong to the selected project."); continue; }
      try {
        const job = await apiJSON("/api/features/" + entry.job_id);
        const clip = job.clips?.[entry.clip_index]; if (!clip) continue;
        const card = document.createElement("section"); card.className = "card";
        const title = document.createElement("h3"); title.textContent = clip.title || "Saved clip";
        const video = document.createElement("video"); video.controls = true; video.playsInline = true;
        const download = document.createElement("button"); download.textContent = "Download original MP4";
        download.onclick = () => downloadClip(clip).catch(error => setStatus(error.message));
        const captions = document.createElement("button"); captions.textContent = "Download captions (VTT)";
        captions.onclick = () => downloadClip(clip, true).catch(error => setStatus(error.message));
        const edit = document.createElement("a"); edit.className = "button"; edit.textContent = "Open editor";
        edit.href = projectURL("editor_C.html", entry.job_id, entry.clip_index);
        card.append(title, video, download, captions, edit); list.appendChild(card); await attachClip(video, clip);
      } catch (error) { setStatus(error.message); }
    }
    if (!list.children.length) list.textContent = "No saved clips. Save a generated clip from the editor first.";
  }

  // Load Clerk and verify the session with FastAPI.
  async function start() {
    if (
      window.location.protocol === "file:"
    ) {
      setStatus(
        "Run Uvicorn and open http://127.0.0.1:8000."
      );

      return;
    }

    try {
      const configResponse = await fetch(
        "/api/auth-config",
        {
          cache: "no-store"
        }
      );

      if (!configResponse.ok) {
        throw new Error(
          "Could not load the backend Clerk configuration. Run app1.py with Uvicorn on port 8000."
        );
      }

      const config =
        await configResponse.json();

      if (
        !/^[a-zA-Z0-9.-]+$/.test(
          config.domain
        )
      ) {
        throw new Error(
          "Invalid Clerk domain."
        );
      }

      await loadScript(
        "https://" +
        config.domain +
        "/npm/@clerk/ui@1/dist/ui.browser.js"
      );

      await loadScript(
        "https://" +
        config.domain +
        "/npm/@clerk/clerk-js@6/dist/clerk.browser.js",
        config.publishable_key
      );

      await window.Clerk.load({
        ui: {
          ClerkUI:
            window.__internal_ClerkUICtor
        }
      });

      if (page === "login") {
        if (window.Clerk.session) {
          await apiJSON(
            "/api/session"
          );

          window.location.replace(
            "projects_C.html"
          );

          return;
        }

        const projectsURL = new URL(
          "projects_C.html",
          window.location.href
        ).href;

        window.Clerk.mountSignIn(
          $("sign-in"),
          {
            routing: "hash",

            forceRedirectUrl:
              projectsURL,

            signUpForceRedirectUrl:
              projectsURL,

            appearance: {
              variables: {
                colorPrimary: "#2c705b",
                borderRadius: "12px"
              }
            }
          }
        );

        setStatus("");

        return;
      }

      if (
        !window.Clerk.session ||
        !window.Clerk.user
      ) {
        redirectToLogin();
        return;
      }

      // Server-side authentication check.
      const session = await apiJSON(
        "/api/session"
      );

      if (
        session.user_id !==
        window.Clerk.user.id
      ) {
        throw new Error(
          "Your account could not be verified. Please sign in again."
        );
      }

      userId = session.user_id;

      window.Clerk.addListener(
        ({ user, session: clerkSession }) => {
          if (
            !user ||
            !clerkSession ||
            user.id !== userId
          ) {
            redirectToLogin();
          }
        }
      );

      showAccount();

      $("protected-page").hidden = false;

      setStatus("");

      if (page === "projects") {
        await initializeProjects();
      }

      if (page !== "projects") await loadProject();

      if (page === "exports") await initializeExports();

      if (page === "canvas") {
        await initializeCanvas();
      }

      if (page === "editor") {
        await initializeEditor();
      }
    } catch (error) {
      setStatus(
        error.message ||
        "Could not load the page."
      );

      console.error(error);
    }
  }

  window.addEventListener(
    "pagehide",
    () => {
      mediaURLs.forEach(url => {
        URL.revokeObjectURL(url);
      });

      if (sourceURL) {
        URL.revokeObjectURL(sourceURL);
      }
    }
  );

  start();
})();