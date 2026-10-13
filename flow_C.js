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

  let userId = null;
  let sourceURL = null;
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
    return "cascade-one-clip-job:" + userId;
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

  function getProjectName() {
    try {
      return (
        localStorage.getItem(
          projectStorageKey()
        ) ||
        "Untitled project"
      );
    } catch {
      return "Untitled project";
    }
  }

  function showAccount() {
    const user = window.Clerk.user;

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
    const clip = job.clips?.[0];

    if (!clip) {
      throw new Error(
        "No matching clip was found. Try a different prompt."
      );
    }

    $("clip-title").textContent =
      clip.title || "Generated clip";

    $("clip-explanation").textContent =
      clip.explanation || "";

    $("clip-timing").textContent =
      "Source: " +
      Number(clip.start).toFixed(1) +
      "–" +
      Number(clip.end).toFixed(1) +
      " seconds";

    $("clip-empty").hidden = true;

    await attachClip(
      $("clip-video"),
      clip
    );

    const editorLink = $("open-editor");

    editorLink.href =
      "editor_C.html?job=" +
      encodeURIComponent(jobId);

    editorLink.removeAttribute(
      "aria-disabled"
    );

    editorLink.classList.remove(
      "disabled-link"
    );

    editorLink.onclick = null;
  }

  async function pollJob(jobId) {
    while (!signedOut) {
      const job = await apiJSON(
        "/jobs/" + encodeURIComponent(jobId)
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
          setStatus("Clip 1 is ready.");

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
    const video = $("clip-video");

    video.pause();
    video.removeAttribute("src");
    video.replaceChildren();
    video.hidden = true;

    $("clip-empty").hidden = false;
    $("clip-title").textContent = "";
    $("clip-explanation").textContent = "";
    $("clip-timing").textContent = "";

    const editorLink = $("open-editor");

    editorLink.setAttribute(
      "aria-disabled",
      "true"
    );

    editorLink.classList.add(
      "disabled-link"
    );

    editorLink.onclick = event => {
      event.preventDefault();

      setStatus(
        "Wait for Clip 1 to finish processing."
      );
    };
  }

  // Projects page
  function initializeProjects() {
    $("project-name").value =
      getProjectName();

    $("project-form").onsubmit = event => {
      event.preventDefault();

      const name =
        $("project-name").value.trim();

      if (!name) return;

      try {
        localStorage.setItem(
          projectStorageKey(),
          name
        );
      } catch {
        // Saving the name is optional.
      }

      window.location.href =
        "canvas_C.html";
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
        $("source-video").files[0];

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
    const jobId = getSavedJob();

    if (jobId) {
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

    // FastAPI verifies that this user owns the job.
    const job = await apiJSON(
      "/jobs/" + encodeURIComponent(jobId)
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

    const clip = job.clips[0];

    $("editor-clip-title").textContent =
      "Clip 1 · " +
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

    setStatus(
      "Clip 1 loaded. Editing controls remain layout placeholders."
    );
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
        initializeProjects();
      }

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