/*
  Cascade visual prototype
  All page filenames use the _C suffix.

  Keep these files together:
  index_C.html
  login_C.html
  projects_C.html
  canvas_C.html
  editor_C.html
  exports_C.html
  styles_C.css
  app_C.js
*/

const $ = selector => document.querySelector(selector);

const $$ = selector => [
  ...document.querySelectorAll(selector)
];

const FILES = {
  index: "index_C.html",
  login: "login_C.html",
  projects: "projects_C.html",
  canvas: "canvas_C.html",
  editor: "editor_C.html",
  exports: "exports_C.html"
};

const STORAGE_KEY = "cascade-prototype-v1";

const page = document.body.dataset.page || "index";

function escapeHTML(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    character => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[character]
  );
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function wait(milliseconds) {
  return new Promise(resolve => {
    setTimeout(resolve, milliseconds);
  });
}

function timestamp(seconds) {
  const total = Math.max(
    0,
    Math.floor(Number(seconds) || 0)
  );

  return (
    Math.floor(total / 60) +
    ":" +
    String(total % 60).padStart(2, "0")
  );
}

function thumbnail(label = "▶ Preview") {
  return `
    <div class="thumb">
      <span>${escapeHTML(label)}</span>
    </div>
  `;
}

const sampleTitles = [
  "The moment everything went wrong",
  "Learning to let go",
  "A small idea, a big change",
  "The advice I wish I had",
  "Behind the first attempt",
  "An unexpected connection"
];

function createInitialState() {
  const clips = {};

  sampleTitles.forEach((title, index) => {
    const id = `c${index + 1}`;

    clips[id] = {
      id,
      title,
      start: 20 + index * 43,
      end: 50 + index * 43,
      branch: index < 4 ? "b1" : "b2",

      reason: index % 2
        ? "A thoughtful pause leads into a clear takeaway."
        : "The setup and unexpected reaction make a complete story."
    };
  });

  return {
    user: null,
    project: "p1",
    selected: ["c1", "c2"],
    active: "c1",
    miniClosed: false,
    last: FILES.canvas,

    projects: [
      {
        id: "p1",
        name: "Conversations by the waterfall",
        status: "Editing",
        modified: Date.now(),
        source: "forest-interview.mp4",

        branches: [
          {
            id: "b1",
            prompt: "Find funny and memorable moments",
            scope: "Original source",
            clips: ["c1", "c2", "c3", "c4"]
          },
          {
            id: "b2",
            prompt: "Find moments about personal growth",
            scope: "Original source",
            clips: ["c5", "c6"]
          }
        ],

        clips
      },
      {
        id: "p2",
        name: "Campus stories",
        status: "Clips ready",
        modified: Date.now() - 86400000,
        source: "campus-stories.mp4",
        branches: [],
        clips: {}
      },
      {
        id: "p3",
        name: "A weekend outside",
        status: "Analyzing",
        modified: Date.now() - 172800000,
        source: "weekend.mp4",
        branches: [],
        clips: {}
      }
    ],

    settings: {},
    chat: {},
    finished: {},
    versions: {}
  };
}

let state;

try {
  state =
    JSON.parse(localStorage.getItem(STORAGE_KEY)) ||
    createInitialState();
} catch {
  state = createInitialState();
}

/* Update any previously saved page name. */

if (state.last) {
  const savedPage = state.last
    .split("/")
    .pop()
    .replace(/_C\.html$/i, "")
    .replace(/\.html$/i, "");

  state.last = FILES[savedPage] || FILES.canvas;
}

let editorTab = "chat";

let canvasZoom = 0.65;

let canvasPan = {
  x: 25,
  y: 65
};

let currentTime = 0;

let playing = false;

let playbackTimer;

let saveTimer;

let toastTimer;

let undoStack = [];

let redoStack = [];

function currentProject() {
  return (
    state.projects.find(project => {
      return project.id === state.project;
    }) ||
    state.projects[0]
  );
}

function currentClip() {
  return currentProject()?.clips[state.active];
}

function editorKey(clipId = state.active) {
  return `${currentProject().id}:${clipId}`;
}

function defaultSettings(duration = 30) {
  return {
    ratio: "16:9",
    fit: "crop",
    x: 50,
    y: 50,
    scale: 100,
    bg: "#18372c",
    safe: false,
    trimStart: 0,
    trimEnd: duration,
    caption: true,
    font: "Arial",
    size: 23,
    color: "#ffffff",
    captionBg: "#17372b",
    placement: "bottom",
    align: "center",
    highlight: false,

    captions: [
      {
        start: 0,
        end: 6,
        text: "Sometimes the best moments happen by accident."
      },
      {
        start: 9,
        end: 17,
        text: "You just have to keep going."
      },
      {
        start: 21,
        end: 29,
        text: "That is where the story begins."
      }
    ],

    broll: [],
    segments: 1,
    reversed: false
  };
}

function getSettings(clipId = state.active) {
  const key = editorKey(clipId);

  if (!state.settings[key]) {
    const clip = currentProject().clips[clipId];

    state.settings[key] = defaultSettings(
      clip ? clip.end - clip.start : 30
    );
  }

  return state.settings[key];
}

function saveState() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(state)
    );

    const status = $("#save-status");

    if (status) {
      status.textContent = "Saving…";

      clearTimeout(saveTimer);

      saveTimer = setTimeout(() => {
        const currentStatus = $("#save-status");

        if (currentStatus) {
          currentStatus.textContent = "Saved locally";
        }
      }, 400);
    }
  } catch {
    showToast(
      "Browser storage is unavailable. Changes will last only while this page stays open."
    );
  }
}

function showToast(message) {
  const toast = $("#toast");

  if (!toast) return;

  toast.textContent = message;

  toast.hidden = false;

  clearTimeout(toastTimer);

  toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 4200);
}

function navigate(destination) {
  const filename = FILES[destination] || destination;

  if (
    filename === FILES.canvas ||
    filename === FILES.editor
  ) {
    state.last = filename;
  }

  saveState();

  window.location.href = filename;
}

function openModal(
  title,
  content,
  onSave = null,
  saveLabel = "Save"
) {
  $("#modal-title").textContent = title;

  $("#modal-body").innerHTML = content;

  const button = $("#modal-save");

  button.textContent = saveLabel;

  button.hidden = !onSave;

  button.onclick = onSave;

  $("#modal-layer").hidden = false;

  $("#modal-close").focus();
}

function closeModal() {
  $("#modal-layer").hidden = true;
}

/* Shared header */

function renderHeader() {
  const name =
    state.user?.name?.split(" ")[0] ||
    "Demo account";

  $("#header").innerHTML = `
    <a class="brand" href="${FILES.index}">
      <span>≋</span>
      Cascade
    </a>

    <div class="row">
      <a class="button" href="${FILES.projects}">
        Projects
      </a>

      <a class="button" href="${FILES.exports}">
        Exports
      </a>

      <span class="pill">
        Visual prototype
      </span>

      <div class="account-wrap">
        <button
          id="account-toggle"
          type="button"
          aria-expanded="false"
        >
          ${escapeHTML(name)} ▾
        </button>

        <div
          id="account-menu"
          class="card account-menu"
          hidden
        >
          <b>
            ${escapeHTML(
              state.user?.name || "Demo creator"
            )}
          </b>

          <p class="muted">
            ${escapeHTML(
              state.user?.email ||
              "creator@example.com"
            )}
            <br>

            <small>
              ID: demo_creator_001
            </small>
          </p>

          <button id="account-settings">
            Account settings
          </button>

          <button id="reset-demo">
            Reset demo
          </button>

          <button id="sign-out">
            ${state.user ? "Sign out" : "Sign in"}
          </button>
        </div>
      </div>
    </div>
  `;

  $("#account-toggle").onclick = () => {
    const menu = $("#account-menu");

    menu.hidden = !menu.hidden;

    $("#account-toggle").setAttribute(
      "aria-expanded",
      String(!menu.hidden)
    );
  };

  $("#account-settings").onclick = () => {
    openModal(
      "Demo account",
      `
        <p>
          ${escapeHTML(
            state.user?.name || "Demo creator"
          )}
        </p>

        <p>
          ${escapeHTML(
            state.user?.email ||
            "creator@example.com"
          )}
        </p>

        <p class="muted">
          User ID: demo_creator_001
        </p>

        <p class="notice">
          This is a local demo account.
          Real authentication will use
          your existing Clerk integration.
        </p>
      `
    );
  };

  $("#sign-out").onclick = () => {
    state.user = null;

    navigate("login");
  };

  $("#reset-demo").onclick = () => {
    openModal(
      "Reset this demo?",
      `
        <p>
          This removes prototype edits and restores
          the sample projects.
        </p>
      `,
      () => {
        state = createInitialState();

        navigate("index");
      },
      "Reset demo"
    );
  };

  $("#modal-close").onclick = closeModal;

  $("#modal-layer").onclick = event => {
    if (event.target.id === "modal-layer") {
      closeModal();
    }
  };

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      closeModal();
    }
  });
}

/* Landing page */

function renderLanding() {
  $("#app").innerHTML = `
    <div class="container">
      <section class="hero">
        <div>
          <p class="eyebrow">
            Find your flow
          </p>

          <h1>
            Turn long videos into clips worth sharing.
          </h1>

          <p>
            Follow an idea. Discover a moment.
            Make it yours. Explore your footage on
            a branching canvas, then shape every clip
            in a conversational editor.
          </p>

          <div class="row">
            <button
              id="get-started"
              class="primary"
            >
              Get started ↗
            </button>

            <button id="resume">
              Start where you left off
            </button>
          </div>

          <p
            style="
              margin-top: 20px;
              font-size: 12px;
            "
          >
            AI discovery · Research assistance ·
            Captions · Creative editing
          </p>
        </div>

        <div class="hero-art">
          <div class="waterfall"></div>

          <div class="preview-card">
            <div class="row between">
              <b>Your ideas, connected.</b>

              <span class="pill">
                Canvas → Editor
              </span>
            </div>

            <div class="flow">
              <b>Source video</b>
              <i></i>
              <b>Find a moment</b>
              <i></i>
              <b>Make a clip</b>
            </div>

            <div class="row">
              <span class="pill">
                Funny moments
              </span>

              <span class="pill">
                A fresh perspective
              </span>

              <span class="pill">
                Your next story
              </span>
            </div>
          </div>
        </div>
      </section>

      <section class="section">
        <p class="eyebrow">
          A creative workspace, from start to finish
        </p>

        <h2>
          Less searching. More storytelling.
        </h2>

        <div class="grid">
          <article class="card">
            <h3>01 / Discover</h3>

            <p class="muted">
              Ask for funny, emotional, or educational
              moments. Keep exploring your original
              footage through new branches.
            </p>
          </article>

          <article class="card">
            <h3>02 / Shape</h3>

            <p class="muted">
              Edit with chat, customize captions,
              reframe your video, and add B-roll
              to bring your story together.
            </p>
          </article>

          <article class="card">
            <h3>03 / Share</h3>

            <p class="muted">
              Save finished versions, choose your
              format, and review the export flow
              before sharing your clips.
            </p>
          </article>
        </div>
      </section>

      <section class="card">
        <p class="eyebrow">
          Create with a little guidance
        </p>

        <h2>
          Follow the story wherever it goes.
        </h2>

        <p class="muted">
          Research suggestions help you choose a
          direction. Captions make the message
          clearer. Your editing chat remembers
          each clip’s changes.
        </p>

        <div class="row">
          <a
            class="button"
            href="${FILES.canvas}"
          >
            Explore the sample canvas
          </a>

          <a
            class="button"
            href="${FILES.editor}"
          >
            Preview the editor
          </a>
        </div>
      </section>

      <footer class="footer row between">
        <span>
          ≋ Cascade — Find your best moments.
        </span>

        <span>
          Upload → Discover → Edit → Export
        </span>
      </footer>
    </div>
  `;

  $("#get-started").onclick = () => {
    navigate(
      state.user ? "projects" : "login"
    );
  };

  $("#resume").onclick = () => {
    navigate(state.last || FILES.projects);
  };
}

/* Demo login */

function renderLogin() {
  $("#app").innerHTML = `
    <div class="auth">
      <div>
        <p class="eyebrow">
          Welcome to your creative flow
        </p>

        <h1>
          Every video has<br>
          a story waiting.
        </h1>

        <div
          class="hero-art"
          style="height: 260px;"
        >
          <div class="waterfall"></div>
        </div>

        <p
          class="muted"
          style="margin-top: 20px;"
        >
          Explore the complete sample workspace.
          No account or connection needed.
        </p>
      </div>

      <div class="card">
        <div class="tabs">
          <button
            id="sign-in-tab"
            class="active"
          >
            Sign in
          </button>

          <button id="sign-up-tab">
            Sign up
          </button>
        </div>

        <h2 id="auth-title">
          Welcome back
        </h2>

        <p class="notice">
          Demo sign-in only.
          Credentials are never sent or saved.
        </p>

        <form id="auth-form">
          <div id="name-field" hidden>
            <label for="auth-name">
              Name
            </label>

            <input
              id="auth-name"
              autocomplete="name"
              placeholder="Your name"
            >
          </div>

          <label for="auth-email">
            Email
          </label>

          <input
            id="auth-email"
            type="email"
            autocomplete="email"
            placeholder="creator@example.com"
            required
          >

          <label for="auth-password">
            Password
          </label>

          <div class="row">
            <input
              id="auth-password"
              type="password"
              autocomplete="off"
              placeholder="Any demo password"
              style="flex: 1;"
            >

            <button
              id="show-password"
              type="button"
            >
              Show
            </button>
          </div>

          <button
            id="forgot-password"
            type="button"
            style="margin: 12px 0;"
          >
            Forgot password?
          </button>

          <button
            class="primary"
            type="submit"
            style="width: 100%;"
          >
            Continue
          </button>
        </form>

        <div
          class="row"
          style="margin-top: 18px;"
        >
          <button id="google-demo">
            Google (demo)
          </button>

          <button id="apple-demo">
            Apple (demo)
          </button>
        </div>

        <button
          id="enter-demo"
          style="
            width: 100%;
            margin-top: 15px;
          "
        >
          Enter demo without signing in →
        </button>
      </div>
    </div>
  `;

  function setMode(signUp) {
    $("#name-field").hidden = !signUp;

    $("#auth-title").textContent = signUp
      ? "Create your account"
      : "Welcome back";

    $("#sign-in-tab").classList.toggle(
      "active",
      !signUp
    );

    $("#sign-up-tab").classList.toggle(
      "active",
      signUp
    );
  }

  $("#sign-in-tab").onclick = () => setMode(false);

  $("#sign-up-tab").onclick = () => setMode(true);

  $("#show-password").onclick = () => {
    const input = $("#auth-password");

    const show = input.type === "password";

    input.type = show ? "text" : "password";

    $("#show-password").textContent = show
      ? "Hide"
      : "Show";
  };

  function enterDemo() {
    state.user = {
      name:
        $("#auth-name").value.trim() ||
        "Demo creator",

      email:
        $("#auth-email").value.trim() ||
        "creator@example.com"
    };

    navigate("projects");
  }

  $("#auth-form").onsubmit = event => {
    event.preventDefault();

    enterDemo();
  };

  $("#enter-demo").onclick = enterDemo;

  $("#google-demo").onclick = enterDemo;

  $("#apple-demo").onclick = enterDemo;

  $("#forgot-password").onclick = () => {
    showToast(
      "Demo only: Clerk will handle real password-reset emails."
    );
  };
}

/* Projects */

function openProject(projectId) {
  state.project = projectId;

  const project = currentProject();

  if (!project.branches.length) {
    const sample = createInitialState().projects[0];

    project.branches = clone(sample.branches);

    project.clips = clone(sample.clips);
  }

  state.selected = state.selected.filter(id => {
    return Boolean(project.clips[id]);
  });

  if (!state.selected.length) {
    state.selected =
      Object.keys(project.clips).slice(0, 2);
  }

  state.active = state.selected[0];

  navigate("canvas");
}

function renderProjects() {
  $("#app").innerHTML = `
    <div class="container">
      <p class="eyebrow">
        Your workspace
      </p>

      <div class="row between">
        <div>
          <h1>Stories in the making.</h1>

          <p class="muted">
            Pick up where you left off,
            or start with something new.
          </p>
        </div>

        <button
          id="new-project"
          class="primary"
        >
          ＋ New project
        </button>
      </div>

      <div class="row toolbar">
        <input
          id="project-search"
          aria-label="Search projects"
          placeholder="Search your projects…"
        >

        <select
          id="project-sort"
          aria-label="Sort projects"
        >
          <option value="recent">
            Recently updated
          </option>

          <option value="name">
            Name A–Z
          </option>
        </select>

        <span
          id="project-count"
          class="muted"
        ></span>
      </div>

      <div
        id="projects-grid"
        class="grid"
      ></div>
    </div>
  `;

  function drawProjects() {
    const search =
      $("#project-search").value.toLowerCase();

    const projects = state.projects.filter(project => {
      return project.name.toLowerCase().includes(search);
    });

    projects.sort(
      $("#project-sort").value === "name"
        ? (a, b) => a.name.localeCompare(b.name)
        : (a, b) => b.modified - a.modified
    );

    $("#project-count").textContent =
      `${projects.length} projects`;

    $("#projects-grid").innerHTML = projects.length
      ? projects.map(project => `
          <article class="card project-card">
            ${thumbnail(
              project.source || "No source video"
            )}

            <div class="row between">
              <span class="pill">
                ${escapeHTML(project.status)}
              </span>

              <small>
                ${Object.keys(project.clips).length}
                clips
              </small>
            </div>

            <h3 style="margin-top: 14px;">
              ${escapeHTML(project.name)}
            </h3>

            <p class="muted">
              Updated
              ${new Date(
                project.modified
              ).toLocaleDateString()}
            </p>

            <div class="row">
              <button
                class="primary"
                data-open-project="${project.id}"
              >
                Open project ↗
              </button>

              <button
                data-project-menu="${project.id}"
                aria-label="Project actions"
              >
                •••
              </button>
            </div>
          </article>
        `).join("")
      : `
          <div class="card empty">
            No projects found.
            Create a project to begin.
          </div>
        `;

    $$("[data-open-project]").forEach(button => {
      button.onclick = () => {
        openProject(button.dataset.openProject);
      };
    });

    $$("[data-project-menu]").forEach(button => {
      button.onclick = () => {
        const project = state.projects.find(item => {
          return item.id === button.dataset.projectMenu;
        });

        openModal(
          "Project settings",
          `
            <label for="rename-project">
              Project name
            </label>

            <input
              id="rename-project"
              value="${escapeHTML(project.name)}"
            >

            <button
              id="delete-project"
              class="danger"
              style="margin-top: 15px;"
            >
              Delete project
            </button>
          `,
          () => {
            project.name =
              $("#rename-project").value.trim() ||
              project.name;

            project.modified = Date.now();

            saveState();

            closeModal();

            drawProjects();
          }
        );

        $("#delete-project").onclick = () => {
          openModal(
            "Delete project?",
            `
              <p>
                Remove ${escapeHTML(project.name)}
                and its prototype data?
              </p>
            `,
            () => {
              state.projects = state.projects.filter(
                item => item.id !== project.id
              );

              [
                state.settings,
                state.chat,
                state.finished,
                state.versions
              ].forEach(collection => {
                Object.keys(collection).forEach(key => {
                  if (key.startsWith(`${project.id}:`)) {
                    delete collection[key];
                  }
                });
              });

              if (state.project === project.id) {
                state.project =
                  state.projects[0]?.id || null;

                state.selected = [];

                state.active = null;
              }

              saveState();

              closeModal();

              drawProjects();
            },
            "Delete"
          );
        };
      };
    });
  }

  drawProjects();

  $("#project-search").oninput = drawProjects;

  $("#project-sort").onchange = drawProjects;

  $("#new-project").onclick = () => {
    openModal(
      "Start a new story",
      `
        <label for="project-name">
          Project name
        </label>

        <input
          id="project-name"
          placeholder="Untitled project"
        >
      `,
      () => {
        const id = `p${Date.now()}`;

        state.projects.push({
          id,

          name:
            $("#project-name").value.trim() ||
            "Untitled project",

          status: "New",
          modified: Date.now(),
          source: "",
          branches: [],
          clips: {}
        });

        state.project = id;

        state.selected = [];

        state.active = null;

        navigate("canvas");
      },
      "Create project"
    );
  };
}

/* Workspace heading */

function workspaceHeading(actions) {
  return `
    <div class="workspace-header">
      <div class="row">
        <a href="${FILES.projects}">
          ← Projects
        </a>

        <div>
          <p class="workspace-title">
            ${escapeHTML(currentProject().name)}
          </p>

          <small id="save-status">
            Saved locally
          </small>
        </div>
      </div>

      <div class="row">
        ${actions}
      </div>
    </div>
  `;
}

/* Canvas */

function renderCanvas() {
  if (!currentProject()) {
    navigate("projects");

    return;
  }

  $("#app").innerHTML = workspaceHeading(`
    <button id="canvas-research">
      ✧ Research
    </button>

    <button
      id="continue-editor"
      class="primary"
    >
      Continue to editor →
    </button>
  `) + `
    <div class="canvas-layout">
      <aside class="discovery">
        <p class="eyebrow">
          01 / Discover
        </p>

        <h3>Start with your source.</h3>

        <div
          id="video-drop"
          class="card"
          style="padding: 12px;"
        >
          ${thumbnail("＋ Drop a video")}

          <label for="video-upload">
            Choose video
          </label>

          <input
            id="video-upload"
            type="file"
            accept="video/*"
          >

          <small id="source-filename">
            ${escapeHTML(
              currentProject().source ||
              "No video chosen"
            )}
          </small>

          <button
            id="use-sample"
            style="
              width: 100%;
              margin-top: 10px;
            "
          >
            Use sample video
          </button>
        </div>

        <p class="notice">
          Sample visuals are illustrative.
          A chosen file is not uploaded;
          only its name is saved.
        </p>

        <label for="discovery-prompt">
          What are you looking for?
        </label>

        <textarea
          id="discovery-prompt"
          placeholder="Find the funniest moments…"
        ></textarea>

        <div class="suggestions">
          <button data-prompt="Find funny moments">
            Funny
          </button>

          <button data-prompt="Find emotional moments">
            Emotional
          </button>

          <button data-prompt="Find educational moments">
            Educational
          </button>
        </div>

        <div class="two">
          <div>
            <label for="clip-count">
              Clips
            </label>

            <select id="clip-count">
              <option>4</option>
              <option>3</option>
              <option>2</option>
            </select>
          </div>

          <div>
            <label for="clip-duration">
              Duration
            </label>

            <select id="clip-duration">
              <option value="30">30 sec</option>
              <option value="15">15 sec</option>
              <option value="60">60 sec</option>
            </select>
          </div>
        </div>

        <label for="discovery-mood">
          Mood / topic
        </label>

        <input
          id="discovery-mood"
          placeholder="Inspiring, funny, personal…"
        >

        <label for="discovery-platform">
          Platform
        </label>

        <select id="discovery-platform">
          <option>Any platform</option>
          <option>TikTok / Reels</option>
          <option>YouTube</option>
        </select>

        <button
          id="generate-clips"
          class="primary"
          style="
            width: 100%;
            margin-top: 16px;
          "
        >
          ✧ Generate sample clips
        </button>

        <p
          id="generation-status"
          class="muted"
          aria-live="polite"
        ></p>
      </aside>

      <div
        id="canvas-shell"
        class="canvas-shell"
      >
        <div class="canvas-controls">
          <button
            id="canvas-zoom-out"
            aria-label="Zoom out"
          >
            −
          </button>

          <button id="canvas-fit">
            Fit
          </button>

          <button
            id="canvas-zoom-in"
            aria-label="Zoom in"
          >
            ＋
          </button>

          <small
            id="canvas-zoom-value"
            style="padding: 8px;"
          ></small>
        </div>

        <div
          id="canvas-board"
          class="board"
        ></div>

        <div
          id="selection-tray"
          class="selection-tray"
        ></div>
      </div>
    </div>
  `;

  drawCanvas();

  $("#continue-editor").onclick = () => {
    if (!state.selected.length) {
      showToast(
        "Select at least one clip to open the editor."
      );

      return;
    }

    state.active = state.selected[0];

    navigate("editor");
  };

  $("#canvas-research").onclick = () => {
    openResearch("canvas");
  };

  $$("[data-prompt]").forEach(button => {
    button.onclick = () => {
      $("#discovery-prompt").value =
        button.dataset.prompt;
    };
  });

  $("#use-sample").onclick = () => {
    currentProject().source = "forest-interview.mp4";

    $("#source-filename").textContent =
      currentProject().source;

    saveState();

    drawCanvas();

    showToast(
      "Sample source selected. Preview uses illustrative visuals."
    );
  };

  function chooseFile(file) {
    if (!file || !file.type.startsWith("video/")) {
      showToast("Choose a video file.");

      return;
    }

    currentProject().source = file.name;

    $("#source-filename").textContent = file.name;

    saveState();

    drawCanvas();

    showToast(
      "Video filename added to the demo. No upload was made."
    );
  }

  $("#video-upload").onchange = event => {
    chooseFile(event.target.files[0]);
  };

  $("#video-drop").ondragover = event => {
    event.preventDefault();
  };

  $("#video-drop").ondrop = event => {
    event.preventDefault();

    chooseFile(event.dataTransfer.files[0]);
  };

  $("#generate-clips").onclick = async () => {
    if (!currentProject().source) {
      showToast(
        "Choose a video or use the sample first."
      );

      return;
    }

    $("#generate-clips").disabled = true;

    for (const stage of [
      "Uploading",
      "Analyzing speech",
      "Analyzing visuals",
      "Finding moments",
      "Preparing clips"
    ]) {
      $("#generation-status").textContent =
        `${stage}… (simulation)`;

      await wait(350);
    }

    const prompt =
      $("#discovery-prompt").value.trim() ||
      "Automatic highlights";

    addBranch(
      [
        prompt,
        $("#discovery-mood").value.trim(),
        $("#discovery-platform").value
      ].filter(Boolean).join(" · "),
      {
        count: Number($("#clip-count").value),
        duration: Number($("#clip-duration").value)
      }
    );

    $("#generation-status").textContent =
      "Sample clips ready.";

    $("#generate-clips").disabled = false;
  };

  $("#canvas-zoom-in").onclick = () => {
    canvasZoom = Math.min(1.4, canvasZoom + 0.1);

    transformCanvas();
  };

  $("#canvas-zoom-out").onclick = () => {
    canvasZoom = Math.max(0.2, canvasZoom - 0.1);

    transformCanvas();
  };

  $("#canvas-fit").onclick = fitCanvas;

  const shell = $("#canvas-shell");

  let drag = null;

  shell.onpointerdown = event => {
    if (
      event.target.closest(
        "button, input, .node, .selection-tray"
      )
    ) {
      return;
    }

    drag = {
      x: event.clientX,
      y: event.clientY,
      panX: canvasPan.x,
      panY: canvasPan.y
    };

    shell.setPointerCapture(event.pointerId);
  };

  shell.onpointermove = event => {
    if (!drag) return;

    canvasPan = {
      x: drag.panX + event.clientX - drag.x,
      y: drag.panY + event.clientY - drag.y
    };

    transformCanvas();
  };

  shell.onpointerup = () => {
    drag = null;
  };

  shell.onpointercancel = () => {
    drag = null;
  };

  shell.onwheel = event => {
    event.preventDefault();

    canvasZoom = Math.max(
      0.2,
      Math.min(
        1.4,
        canvasZoom +
          (event.deltaY > 0 ? -0.04 : 0.04)
      )
    );

    transformCanvas();
  };
}

function addBranch(prompt, options = {}) {
  const project = currentProject();

  const branchId =
    `b${Date.now()}${Math.floor(Math.random() * 1000)}`;

  const count = options.count || 3;

  const duration = options.duration || 30;

  const parent = options.parent
    ? project.clips[options.parent]
    : null;

  const clipIds = [];

  const offset = Object.keys(project.clips).length;

  for (let index = 0; index < count; index++) {
    const id = `${branchId}_c${index}`;

    const start = parent && options.variation
      ? parent.start
      : (35 + (offset + index) * 22) % 480;

    project.clips[id] = {
      id,

      title: options.variation && parent
        ? `${parent.title} · ${options.variation}`
        : sampleTitles[
            (offset + index) % sampleTitles.length
          ],

      start,
      end: start + duration,
      branch: branchId,
      reason: `Demo suggestion: ${prompt}`
    };

    clipIds.push(id);
  }

  project.branches.push({
    id: branchId,
    prompt,
    clips: clipIds,
    parent: options.parent || null,

    scope: options.variation
      ? "Selected clip"
      : "Original source"
  });

  project.modified = Date.now();

  project.status = "Clips ready";

  saveState();

  drawCanvas();

  showToast(
    "Sample branch added. These are simulated moments."
  );
}

function transformCanvas() {
  const board = $("#canvas-board");

  if (!board) return;

  board.style.transform =
    `translate(${canvasPan.x}px, ${canvasPan.y}px) ` +
    `scale(${canvasZoom})`;

  $("#canvas-zoom-value").textContent =
    `${Math.round(canvasZoom * 100)}%`;
}

function fitCanvas() {
  const project = currentProject();

  const shell = $("#canvas-shell");

  const widestBranch = Math.max(
    1,
    ...project.branches.map(branch => branch.clips.length)
  );

  const width = 570 + widestBranch * 280;

  const height = Math.max(
    650,
    project.branches.length * 320
  );

  canvasZoom = Math.max(
    0.15,
    Math.min(
      1,
      (shell.clientWidth - 40) / width,
      (shell.clientHeight - 150) / height
    )
  );

  canvasPan = {
    x: 20,
    y: 65
  };

  transformCanvas();
}

function drawCanvas() {
  const board = $("#canvas-board");

  if (!board) return;

  const project = currentProject();

  let connections = "";

  let nodes = `
    <div class="node source">
      ${thumbnail("Original video")}

      <h3 style="margin-top: 12px;">
        ${escapeHTML(
          project.source || "Choose your source"
        )}
      </h3>

      <small>
        Source footage · Demo 08:42
      </small>

      <p class="muted">
        Discovery branches search this original video.
      </p>

      <button id="source-preview">
        Preview source
      </button>
    </div>
  `;

  project.branches.forEach((branch, branchIndex) => {
    const y = 30 + branchIndex * 320;

    let sourceX = 225;

    let sourceY = 330;

    if (branch.parent && project.clips[branch.parent]) {
      const parentClip = project.clips[branch.parent];

      const parentBranchIndex =
        project.branches.findIndex(item => {
          return item.id === parentClip.branch;
        });

      const parentBranch =
        project.branches[parentBranchIndex];

      if (parentBranch) {
        const parentClipIndex =
          parentBranch.clips.indexOf(parentClip.id);

        sourceX = 805 + parentClipIndex * 280;

        sourceY = 130 + parentBranchIndex * 320;
      }
    }

    connections += `
      <path
        d="
          M ${sourceX} ${sourceY}
          C ${sourceX + 70} ${sourceY},
            270 ${y + 95},
            310 ${y + 95}
        "
      />
    `;

    nodes += `
      <div
        class="node prompt"
        style="
          left: 310px;
          top: ${y + 25}px;
        "
      >
        <span class="pill">
          ${escapeHTML(branch.scope || "Original source")}
        </span>

        <h3 style="margin-top: 12px;">
          ${escapeHTML(branch.prompt)}
        </h3>

        <small>
          ${branch.clips.length} suggestions
        </small>

        <button
          data-collapse="${branch.id}"
          style="margin-top: 10px;"
        >
          ${branch.collapsed ? "Expand" : "Collapse"}
          branch
        </button>
      </div>
    `;

    if (branch.collapsed) return;

    branch.clips.forEach((clipId, clipIndex) => {
      const clip = project.clips[clipId];

      const x = 570 + clipIndex * 280;

      connections += `
        <path
          d="
            M 500 ${y + 95}
            C 540 ${y + 95},
              ${x - 30} ${y + 95},
              ${x} ${y + 95}
          "
        />
      `;

      const selected = state.selected.includes(clipId);

      nodes += `
        <div
          class="node clip ${selected ? "selected" : ""}"
          style="
            left: ${x}px;
            top: ${y}px;
          "
        >
          ${thumbnail("▶ Sample moment")}

          <div class="row between">
            <h3>
              ${escapeHTML(clip.title)}
            </h3>

            <input
              type="checkbox"
              data-select="${clipId}"
              aria-label="Select ${escapeHTML(clip.title)}"
              ${selected ? "checked" : ""}
            >
          </div>

          <small>
            ${clip.end - clip.start}s ·
            Source
            ${timestamp(clip.start)}–${timestamp(clip.end)}
          </small>

          <p class="muted">
            ${escapeHTML(clip.reason)}
          </p>

          <div class="node-actions">
            <button data-clip-details="${clipId}">
              Preview / details
            </button>

            <button data-clip-more="${clipId}">
              ＋ More
            </button>
          </div>
        </div>
      `;
    });
  });

  const width = Math.max(
    1900,
    ...project.branches.map(branch => {
      return 570 + branch.clips.length * 280;
    })
  );

  const height = Math.max(
    1100,
    project.branches.length * 320
  );

  board.style.width = `${width}px`;

  board.style.height = `${height}px`;

  board.innerHTML = `
    <svg
      class="connections"
      width="${width}"
      height="${height}"
    >
      <g
        fill="none"
        stroke="#6fa689"
        stroke-width="1.7"
      >
        ${connections}
      </g>
    </svg>

    ${nodes}
  `;

  transformCanvas();

  $("#source-preview").onclick = () => {
    openModal(
      "Source preview",
      `
        ${thumbnail("Illustrative source preview")}

        <p class="notice">
          This prototype uses sample visuals.
          Video processing is not connected.
        </p>
      `
    );
  };

  $$("[data-select]").forEach(input => {
    input.onchange = () => {
      toggleSelection(input.dataset.select);

      drawCanvas();
    };
  });

  $$("[data-collapse]").forEach(button => {
    button.onclick = () => {
      const branch = project.branches.find(item => {
        return item.id === button.dataset.collapse;
      });

      branch.collapsed = !branch.collapsed;

      saveState();

      drawCanvas();
    };
  });

  $$("[data-clip-details]").forEach(button => {
    button.onclick = () => {
      openClipDetails(button.dataset.clipDetails);
    };
  });

  $$("[data-clip-more]").forEach(button => {
    button.onclick = () => {
      openClipActions(button.dataset.clipMore);
    };
  });

  drawSelectionTray();
}

function toggleSelection(clipId) {
  state.selected = state.selected.includes(clipId)
    ? state.selected.filter(id => id !== clipId)
    : [...state.selected, clipId];

  saveState();
}

function drawSelectionTray() {
  $("#selection-tray").innerHTML = `
    <b>
      ${state.selected.length} selected
    </b>

    ${state.selected.map(clipId => `
      <button data-remove-selection="${clipId}">
        ${escapeHTML(
          currentProject().clips[clipId]?.title.slice(0, 23)
        )} ×
      </button>
    `).join("")}

    <small>
      Drag empty canvas to pan · Scroll to zoom
    </small>
  `;

  $$("[data-remove-selection]").forEach(button => {
    button.onclick = () => {
      toggleSelection(button.dataset.removeSelection);

      drawCanvas();
    };
  });
}

function openClipDetails(clipId) {
  const clip = currentProject().clips[clipId];

  openModal(
    clip.title,
    `
      ${thumbnail("Sample clip preview")}

      <p>
        Source
        ${timestamp(clip.start)}–${timestamp(clip.end)}
        · ${clip.end - clip.start} seconds
      </p>

      <p>${escapeHTML(clip.reason)}</p>

      <p class="notice">
        This moment is sample content,
        not an AI-generated cut.
      </p>
    `,
    () => {
      if (!state.selected.includes(clipId)) {
        state.selected.push(clipId);
      }

      saveState();

      closeModal();

      drawCanvas();
    },
    "Select clip"
  );
}

function openClipActions(clipId) {
  const clip = currentProject().clips[clipId];

  openModal(
    "Explore this moment",
    `
      <p>${escapeHTML(clip.title)}</p>

      <p class="notice">
        Find more searches the original video.
        Variations change the selected clip.
      </p>

      <button id="find-more">
        Find more like this
      </button>

      <label for="variation-type">
        Create variation
      </label>

      <select id="variation-type">
        <option>Shorter</option>
        <option>Longer</option>
        <option>Different emphasis</option>
      </select>
    `,
    () => {
      const variation = $("#variation-type").value;

      const originalDuration = clip.end - clip.start;

      const duration = variation === "Shorter"
        ? Math.max(5, originalDuration - 10)
        : variation === "Longer"
          ? originalDuration + 15
          : originalDuration;

      addBranch(
        `Create ${variation.toLowerCase()} variation`,
        {
          parent: clipId,
          variation,
          duration,
          count: 1
        }
      );

      closeModal();
    },
    "Create variation"
  );

  $("#find-more").onclick = () => {
    addBranch(
      `More like: ${clip.title}`,
      {
        parent: clipId,
        count: 3,
        duration: 30
      }
    );

    closeModal();
  };
}

/* Research */

function openResearch(scope = "editor") {
  openModal(
    "Research assistant",
    `
      <p class="notice">
        Demo analysis · Illustrative references,
        not live research
      </p>

      <label for="research-question">
        What would you like to explore?
      </label>

      <input
        id="research-question"
        value="What makes a strong short-form opening?"
      >

      <button
        id="research-analyze"
        style="margin-top: 12px;"
      >
        Analyze (demo)
      </button>

      <div id="research-result">
        <h3 style="margin-top: 20px;">
          Make the first moment count.
        </h3>

        <p class="muted">
          For this sample interview, lead with
          the unexpected reaction and leave enough
          context for the payoff. Try a shorter
          opening, readable captions, and a
          vertical frame.
        </p>

        <p>
          <a
            href="https://support.google.com/youtube/"
            target="_blank"
            rel="noopener"
          >
            YouTube Help — example reference
          </a>
        </p>

        <p>
          <a
            href="https://www.tiktok.com/creators/creator-portal/"
            target="_blank"
            rel="noopener"
          >
            TikTok Creator Portal — example reference
          </a>
        </p>

        <small>
          No claims have been verified against these
          links. Analysis is sample content.
        </small>
      </div>
    `,
    () => {
      const question = $("#research-question").value;

      closeModal();

      if (scope === "canvas") {
        if (!currentProject().source) {
          showToast(
            "Choose a video or use the sample first."
          );

          return;
        }

        addBranch(`Research suggestion: ${question}`);
      } else {
        updateSettings(settings => {
          settings.ratio = "9:16";

          settings.trimStart = Math.min(
            settings.trimEnd - 1,
            settings.trimStart + 2
          );
        });

        showToast(
          "Demo suggestion applied: vertical framing and a tighter opening."
        );
      }
    },
    scope === "canvas"
      ? "Find clips using suggestion"
      : "Apply editing suggestion"
  );

  $("#research-analyze").onclick = () => {
    $("#research-result").hidden = false;

    showToast(
      "Sample analysis shown. No external research request was made."
    );
  };
}

/* Editing state, undo, and redo */

function updateSettings(change, applyToAll = false) {
  const ids = applyToAll
    ? [...state.selected]
    : [state.active];

  const before = {};

  ids.forEach(id => {
    before[id] = clone(getSettings(id));

    change(getSettings(id));
  });

  undoStack.push(before);

  redoStack = [];

  saveState();

  if (page === "editor") {
    renderEditorWorkspace();
  }
}

function restoreHistory(from, to) {
  if (!from.length) {
    showToast("No more changes in this session.");

    return;
  }

  const snapshot = from.pop();

  const current = {};

  Object.keys(snapshot).forEach(id => {
    current[id] = clone(getSettings(id));

    state.settings[editorKey(id)] = clone(snapshot[id]);
  });

  to.push(current);

  saveState();

  renderEditorWorkspace();
}

function undoEdit() {
  restoreHistory(undoStack, redoStack);
}

function redoEdit() {
  restoreHistory(redoStack, undoStack);
}

/* Editor */

function renderEditor() {
  const project = currentProject();

  if (!project || !Object.keys(project.clips).length) {
    navigate("canvas");

    return;
  }

  state.selected = state.selected.filter(id => {
    return Boolean(project.clips[id]);
  });

  if (!state.selected.length) {
    state.selected = [Object.keys(project.clips)[0]];
  }

  if (!state.selected.includes(state.active)) {
    state.active = state.selected[0];
  }

  saveState();

  renderEditorWorkspace();
}

function renderEditorWorkspace() {
  stopPlayback();

  const project = currentProject();

  const clip = currentClip();

  const settings = getSettings();

  const duration = settings.trimEnd - settings.trimStart;

  const finished = state.finished[editorKey()];

  const newerDraft = finished &&
    JSON.stringify(finished.settings) !==
    JSON.stringify(settings);

  $("#app").innerHTML = workspaceHeading(`
    <a class="button" href="${FILES.canvas}">
      ← Canvas
    </a>

    <button id="toggle-mini">
      Canvas panel
    </button>

    <button id="undo-edit" aria-label="Undo">
      ↶
    </button>

    <button id="redo-edit" aria-label="Redo">
      ↷
    </button>

    <button id="version-history">
      Versions
    </button>

    <button
      id="save-finished"
      class="primary"
    >
      Save finished clip
    </button>

    <a class="button" href="${FILES.exports}">
      Exports ↗
    </a>
  `) + `
    <div
      class="editor-layout ${
        state.miniClosed ? "closed" : ""
      }"
    >
      <aside
        class="mini"
        ${state.miniClosed ? "hidden" : ""}
      >
        <p class="eyebrow">
          Project canvas
        </p>

        <div class="row">
          <button
            id="mini-zoom-out"
            style="width: auto;"
          >
            −
          </button>

          <button
            id="mini-zoom-in"
            style="width: auto;"
          >
            ＋
          </button>
        </div>

        <div
          style="
            max-height: 600px;
            overflow: auto;
          "
        >
          <div id="mini-content">
            <small>
              ◎ ${escapeHTML(project.source)}
            </small>

            ${project.branches.map(branch => `
              <details open>
                <summary
                  style="
                    margin: 12px 0;
                    font-size: 11px;
                    cursor: pointer;
                  "
                >
                  ${escapeHTML(branch.prompt)}
                </summary>

                <div class="mini-tree">
                  ${branch.clips.map(id => `
                    <button
                      data-mini-clip="${id}"
                      class="${
                        id === state.active ? "active" : ""
                      }"
                    >
                      ${
                        state.selected.includes(id)
                          ? "✓"
                          : "＋"
                      }
                      ${escapeHTML(project.clips[id].title)}
                    </button>
                  `).join("")}
                </div>
              </details>
            `).join("")}
          </div>
        </div>

        <small>
          Scroll to explore.
          Select a moment to preview, add, or switch.
        </small>
      </aside>

      <main class="stage-area">
        <div class="row between">
          <small class="eyebrow">
            02 / Shape your story
          </small>

          <button id="combine-clips">
            Combine clips
          </button>
        </div>

        <div class="clip-strip">
          ${state.selected.map(id => `
            <button
              data-switch-clip="${id}"
              class="${id === state.active ? "active" : ""}"
            >
              ${escapeHTML(project.clips[id].title)}
            </button>
          `).join("")}
        </div>

        <h3>${escapeHTML(clip.title)}</h3>

        <div
          id="preview-stage"
          class="stage"
        >
          <div
            id="preview-frame"
            class="frame"
          >
            ${thumbnail(
              "Sample interview · Forest conversations"
            )}

            <div
              id="caption-overlay"
              class="caption-overlay"
            ></div>

            <div
              id="broll-overlay"
              class="broll-overlay"
              hidden
            ></div>

            <div
              id="safe-overlay"
              class="safe"
              hidden
            ></div>
          </div>
        </div>

        <div class="player-controls">
          <button
            id="play-preview"
            aria-label="Play or pause"
          >
            ▶
          </button>

          <small id="preview-time">
            ${timestamp(currentTime)} /
            ${timestamp(duration)}
          </small>

          <input
            id="preview-seek"
            type="range"
            min="0"
            max="${duration}"
            step="0.1"
            value="${currentTime}"
            aria-label="Seek"
          >

          <button id="preview-sound">
            Sound
          </button>

          <button
            id="preview-fullscreen"
            aria-label="Fullscreen"
          >
            ⛶
          </button>
        </div>

        <p class="notice">
          Illustrative preview.
          Playback animates the sample timeline;
          no video is being rendered.
          ${newerDraft ? "• Newer draft changes" : ""}
        </p>

        <div class="timeline">
          <div class="row between">
            <b>Timeline</b>

            <div class="row">
              <button id="split-segment">
                Split
              </button>

              <button id="delete-segment">
                Delete
              </button>

              <button id="arrange-segments">
                Arrange
              </button>
            </div>
          </div>

          <div class="ruler">
            <span>00:00</span>
            <span>${timestamp(duration / 3)}</span>
            <span>${timestamp(duration * 2 / 3)}</span>
            <span>${timestamp(duration)}</span>
          </div>

          <div
            id="timeline-playhead"
            class="playhead"
          ></div>

          ${renderTimelineTracks(settings)}

          <div class="two">
            <div>
              <label for="trim-start">
                Trim start (seconds)
              </label>

              <input
                id="trim-start"
                type="number"
                min="0"
                max="${settings.trimEnd - 1}"
                value="${settings.trimStart}"
              >
            </div>

            <div>
              <label for="trim-end">
                Trim end (seconds)
              </label>

              <input
                id="trim-end"
                type="number"
                min="${settings.trimStart + 1}"
                max="${clip.end - clip.start}"
                value="${settings.trimEnd}"
              >
            </div>
          </div>

          <label for="timeline-zoom">
            Timeline zoom
          </label>

          <input
            id="timeline-zoom"
            type="range"
            min="1"
            max="3"
            step="0.1"
            value="1"
          >
        </div>
      </main>

      <aside class="right-panel">
        <div class="tabs" role="tablist">
          ${[
            ["chat", "Chat"],
            ["captions", "Captions"],
            ["ratio", "Aspect ratio"],
            ["broll", "B-roll"]
          ].map(([id, label]) => `
            <button
              role="tab"
              data-editor-tab="${id}"
              aria-selected="${editorTab === id}"
              class="${editorTab === id ? "active" : ""}"
            >
              ${label}
            </button>
          `).join("")}
        </div>

        <div id="editor-tab-body"></div>
      </aside>
    </div>
  `;

  bindEditorControls();

  renderEditorTab();

  updatePreview();
}

function renderTimelineTracks(settings) {
  const tracks = [
    [
      "Video",
      "video",
      `${settings.segments} segment(s)${
        settings.reversed ? " · Reversed order" : ""
      }`,
      true
    ],
    [
      "Audio",
      "audio",
      "Sample speech waveform",
      true
    ],
    [
      "Captions",
      "caption-track",
      "Speech captions",
      settings.caption
    ],
    [
      "B-roll",
      "broll-track",
      settings.broll[0]?.name || "",
      settings.broll.length > 0
    ]
  ];

  return tracks.map(
    ([name, className, text, visible]) => `
      <div class="track">
        <small>${name}</small>

        <div class="track-lane">
          ${visible ? `
            <div class="track-block ${className}">
              ${name === "Video" ? `
                <span
                  class="trim-grip left"
                  data-trim-grip="start"
                  title="Drag to trim start"
                >
                  ⋮
                </span>
              ` : ""}

              ${escapeHTML(text)}

              ${name === "Video" ? `
                <span
                  class="trim-grip right"
                  data-trim-grip="end"
                  title="Drag to trim end"
                >
                  ⋮
                </span>
              ` : ""}
            </div>
          ` : ""}
        </div>
      </div>
    `
  ).join("");
}

function bindEditorControls() {
  $("#toggle-mini").onclick = () => {
    state.miniClosed = !state.miniClosed;

    saveState();

    renderEditorWorkspace();
  };

  let miniZoom = 1;

  $("#mini-zoom-in").onclick = () => {
    miniZoom = Math.min(1.5, miniZoom + 0.1);

    $("#mini-content").style.zoom = miniZoom;
  };

  $("#mini-zoom-out").onclick = () => {
    miniZoom = Math.max(0.6, miniZoom - 0.1);

    $("#mini-content").style.zoom = miniZoom;
  };

  $("#undo-edit").onclick = undoEdit;

  $("#redo-edit").onclick = redoEdit;

  $("#version-history").onclick = openVersionHistory;

  $("#save-finished").onclick = saveFinishedClip;

  $("#combine-clips").onclick = combineClips;

  $$("[data-switch-clip]").forEach(button => {
    button.onclick = () => {
      switchClip(button.dataset.switchClip);
    };
  });

  $$("[data-mini-clip]").forEach(button => {
    button.onclick = () => {
      const id = button.dataset.miniClip;

      const clip = currentProject().clips[id];

      openModal(
        clip.title,
        `
          ${thumbnail("Sample moment")}

          <p class="muted">
            ${escapeHTML(clip.reason)}
          </p>
        `,
        () => {
          if (!state.selected.includes(id)) {
            state.selected.push(id);
          }

          closeModal();

          switchClip(id);
        },
        state.selected.includes(id)
          ? "Switch to clip"
          : "Add to editor"
      );
    };
  });

  $$("[data-editor-tab]").forEach(button => {
    button.onclick = () => {
      editorTab = button.dataset.editorTab;

      renderEditorWorkspace();
    };
  });

  $("#play-preview").onclick = togglePlayback;

  $("#preview-seek").oninput = event => {
    currentTime = Number(event.target.value);

    updatePreview();
  };

  $("#preview-sound").onclick = () => {
    showToast(
      "The illustrative sample preview has no audio."
    );
  };

  $("#preview-fullscreen").onclick = () => {
    const stage = $("#preview-stage");

    if (!stage.requestFullscreen) {
      showToast(
        "Fullscreen is unavailable in this browser."
      );

      return;
    }

    stage.requestFullscreen().catch(() => {
      showToast("Fullscreen could not be opened.");
    });
  };

  $("#trim-start").onchange = event => {
    const value = Number(event.target.value);

    updateSettings(settings => {
      settings.trimStart = Math.max(
        0,
        Math.min(value, settings.trimEnd - 1)
      );
    });
  };

  $("#trim-end").onchange = event => {
    const value = Number(event.target.value);

    const sourceDuration =
      currentClip().end - currentClip().start;

    updateSettings(settings => {
      settings.trimEnd = Math.min(
        sourceDuration,
        Math.max(settings.trimStart + 1, value)
      );
    });
  };

  $("#split-segment").onclick = () => {
    updateSettings(settings => {
      settings.segments += 1;
    });

    showToast(
      `Demo split added at ${timestamp(currentTime)}.`
    );
  };

  $("#delete-segment").onclick = () => {
    updateSettings(settings => {
      settings.segments = Math.max(
        1,
        settings.segments - 1
      );

      settings.trimEnd = Math.max(
        settings.trimStart + 1,
        settings.trimEnd - 2
      );
    });

    showToast(
      "Demo segment removed and duration shortened."
    );
  };

  $("#arrange-segments").onclick = () => {
    updateSettings(settings => {
      settings.reversed = !settings.reversed;
    });

    showToast("Demo segment order updated.");
  };

  $("#timeline-zoom").oninput = event => {
    const zoom = Number(event.target.value);

    $$(".track-block.video, .track-block.audio")
      .forEach(block => {
        block.style.width = `${zoom * 100}%`;
      });
  };

  bindTrimGrips();
}

function bindTrimGrips() {
  $$("[data-trim-grip]").forEach(grip => {
    grip.onpointerdown = event => {
      event.preventDefault();

      const startX = event.clientX;

      const initial = clone(getSettings());

      const isStart =
        grip.dataset.trimGrip === "start";

      let value = isStart
        ? initial.trimStart
        : initial.trimEnd;

      grip.setPointerCapture(event.pointerId);

      grip.onpointermove = moveEvent => {
        const delta = Math.round(
          (moveEvent.clientX - startX) / 8
        );

        value = isStart
          ? Math.max(
              0,
              Math.min(
                initial.trimEnd - 1,
                initial.trimStart + delta
              )
            )
          : Math.max(
              initial.trimStart + 1,
              Math.min(
                currentClip().end - currentClip().start,
                initial.trimEnd + delta
              )
            );

        $(
          isStart ? "#trim-start" : "#trim-end"
        ).value = value;
      };

      grip.onpointerup = () => {
        grip.onpointermove = null;

        updateSettings(settings => {
          settings[
            isStart ? "trimStart" : "trimEnd"
          ] = value;
        });
      };
    };
  });
}

function switchClip(clipId) {
  stopPlayback();

  state.active = clipId;

  currentTime = 0;

  undoStack = [];

  redoStack = [];

  saveState();

  renderEditorWorkspace();
}

function stopPlayback() {
  playing = false;

  clearInterval(playbackTimer);
}

function togglePlayback() {
  if (playing) {
    stopPlayback();

    $("#play-preview").textContent = "▶";

    return;
  }

  playing = true;

  $("#play-preview").textContent = "Ⅱ";

  playbackTimer = setInterval(() => {
    const settings = getSettings();

    const duration =
      settings.trimEnd - settings.trimStart;

    currentTime += 0.1;

    if (currentTime >= duration) {
      currentTime = 0;

      stopPlayback();

      $("#play-preview").textContent = "▶";
    }

    updatePreview();
  }, 100);
}

function updatePreview() {
  const frame = $("#preview-frame");

  if (!frame) return;

  const settings = getSettings();

  const duration = settings.trimEnd - settings.trimStart;

  currentTime = Math.min(currentTime, duration);

  frame.style.aspectRatio =
    settings.ratio.replace(":", " / ");

  frame.style.background = settings.bg;

  const illustration = frame.querySelector(".thumb");

  illustration.style.width =
    settings.fit === "fit" ? "90%" : "100%";

  illustration.style.height =
    settings.fit === "fit" ? "85%" : "100%";

  illustration.style.margin =
    settings.fit === "fit" ? "auto" : "0";

  illustration.style.transform =
    `translate(${(settings.x - 50) / 5}%, ` +
    `${(settings.y - 50) / 5}%) ` +
    `scale(${settings.scale / 100})`;

  const captionTime = currentTime + settings.trimStart;

  const activeCaption = settings.captions.find(caption => {
    return (
      captionTime >= caption.start &&
      captionTime < caption.end
    );
  });

  const captionOverlay = $("#caption-overlay");

  captionOverlay.hidden =
    !settings.caption || !activeCaption;

  captionOverlay.textContent =
    activeCaption?.text || "";

  captionOverlay.style.fontFamily = settings.font;

  captionOverlay.style.fontSize = `${settings.size}px`;

  captionOverlay.style.color = settings.color;

  captionOverlay.style.background = settings.captionBg;

  captionOverlay.style.textAlign = settings.align;

  captionOverlay.style.top =
    settings.placement === "top" ? "12%" : "auto";

  captionOverlay.style.bottom =
    settings.placement === "top"
      ? "auto"
      : settings.placement === "middle"
        ? "42%"
        : "12%";

  if (settings.highlight && activeCaption) {
    const words = activeCaption.text.split(" ");

    const wordIndex =
      Math.floor(currentTime * 2) % words.length;

    captionOverlay.innerHTML = words.map((word, index) => {
      return index === wordIndex
        ? `<mark>${escapeHTML(word)}</mark>`
        : escapeHTML(word);
    }).join(" ");
  }

  $("#safe-overlay").hidden = !settings.safe;

  const activeAsset = settings.broll.find(asset => {
    return (
      currentTime >= asset.start &&
      currentTime < asset.start + asset.duration
    );
  });

  const overlay = $("#broll-overlay");

  overlay.hidden = !activeAsset;

  if (activeAsset) {
    overlay.textContent = activeAsset.name;

    const size = activeAsset.mode === "Full frame"
      ? 100
      : activeAsset.scale || 35;

    overlay.style.width = `${size}%`;

    overlay.style.height = `${size}%`;

    const bottomLeft =
      activeAsset.position === "Bottom left";

    overlay.style.top = bottomLeft ? "auto" : "0";

    overlay.style.bottom = bottomLeft ? "0" : "auto";

    overlay.style.right = bottomLeft ? "auto" : "0";

    overlay.style.left = bottomLeft ? "0" : "auto";
  }

  const brollTrack = $(".broll-track");

  if (brollTrack && settings.broll.length) {
    const asset = settings.broll[0];

    brollTrack.style.left =
      `${asset.start / duration * 100}%`;

    brollTrack.style.width =
      `${Math.min(100, asset.duration / duration * 100)}%`;
  }

  $("#preview-time").textContent =
    `${timestamp(currentTime)} / ${timestamp(duration)}`;

  $("#preview-seek").value = currentTime;

  const availableWidth = Math.max(
    0,
    $(".timeline").clientWidth - 110
  );

  $("#timeline-playhead").style.left =
    `${80 + availableWidth * currentTime / duration}px`;
}

/* Editor tabs */

function renderEditorTab() {
  const renderers = {
    chat: renderChatTab,
    captions: renderCaptionsTab,
    ratio: renderRatioTab,
    broll: renderBrollTab
  };

  renderers[editorTab]();
}

function bindSetting(
  elementId,
  field,
  convert = value => value
) {
  $(`#${elementId}`).onchange = event => {
    const element = event.target;

    const value = element.type === "checkbox"
      ? element.checked
      : element.value;

    updateSettings(settings => {
      settings[field] = convert(value);
    });
  };
}

/* Chat */

function renderChatTab() {
  const key = editorKey();

  state.chat[key] ??= [
    {
      role: "assistant",

      text:
        "This sample moment has a clear setup and payoff. Try a tighter opening or captions to bring out the story."
    }
  ];

  $("#editor-tab-body").innerHTML = `
    <span class="pill">
      Conversational editing · demo
    </span>

    <label for="chat-scope">
      Apply changes to
    </label>

    <select id="chat-scope">
      <option>Active clip</option>
      <option>All selected clips</option>
    </select>

    <div>
      ${state.chat[key].map(message => `
        <div class="chat-message ${message.role}">
          <small>
            ${
              message.role === "user"
                ? "You"
                : "Cascade assistant"
            }
          </small>

          ${escapeHTML(message.text)}
        </div>
      `).join("")}
    </div>

    <div class="suggestions">
      ${[
        "Remove the first two seconds",
        "Make this vertical",
        "Make the captions yellow",
        "Turn captions off",
        "Analyze the opening",
        "Suggest B-roll"
      ].map(text => `
        <button
          data-chat-suggestion="${escapeHTML(text)}"
        >
          ${text}
        </button>
      `).join("")}
    </div>

    <form id="chat-form">
      <label for="chat-message">
        Tell Cascade what to change
      </label>

      <textarea
        id="chat-message"
        placeholder="Make this vertical…"
        required
      ></textarea>

      <div class="row" style="margin-top: 12px;">
        <button class="primary" type="submit">
          Send ↑
        </button>

        <button
          id="editor-research"
          type="button"
        >
          ✧ Research / analyze
        </button>
      </div>

      <small
        id="chat-status"
        aria-live="polite"
      ></small>
    </form>
  `;

  $("#chat-form").onsubmit = event => {
    event.preventDefault();

    sendChat(
      $("#chat-message").value,
      $("#chat-scope").value === "All selected clips"
    );
  };

  $$("[data-chat-suggestion]").forEach(button => {
    button.onclick = () => {
      sendChat(
        button.dataset.chatSuggestion,
        $("#chat-scope").value === "All selected clips"
      );
    };
  });

  $("#editor-research").onclick = () => {
    openResearch("editor");
  };
}

async function sendChat(text, applyToAll) {
  text = text.trim();

  if (!text) return;

  const key = editorKey();

  state.chat[key].push({
    role: "user",
    text
  });

  saveState();

  renderChatTab();

  $("#chat-status").textContent =
    "Applying demo instruction…";

  await wait(400);

  const instruction = text.toLowerCase();

  let response;

  if (instruction.includes("undo")) {
    undoEdit();

    response =
      "Restored the previous edit in this session.";
  } else if (instruction.includes("vertical")) {
    updateSettings(settings => {
      settings.ratio = "9:16";
    }, applyToAll);

    response = "Changed the frame to 9:16.";
  } else if (instruction.includes("yellow")) {
    updateSettings(settings => {
      settings.color = "#ffdd33";

      settings.caption = true;
    }, applyToAll);

    response = "Caption text is now yellow.";
  } else if (instruction.includes("captions off")) {
    updateSettings(settings => {
      settings.caption = false;
    }, applyToAll);

    response = "Turned captions off.";
  } else if (
    instruction.includes("first two seconds")
  ) {
    updateSettings(settings => {
      settings.trimStart = Math.min(
        settings.trimEnd - 1,
        settings.trimStart + 2
      );
    }, applyToAll);

    response = "Removed two seconds from the opening.";
  } else if (instruction.includes("b-roll")) {
    response =
      "Try a forest canopy cutaway during the pause. Use the B-roll tab to add the sample asset.";
  } else if (
    instruction.includes("analy") ||
    instruction.includes("opening")
  ) {
    response =
      "Demo analysis: open with the surprising reaction and shorten the setup. The Research panel lets you apply a tighter vertical edit.";
  } else {
    response =
      "This prototype supports trimming the first two seconds, vertical framing, yellow captions, captions off, opening analysis, B-roll suggestions, and undo.";
  }

  state.chat[key].push({
    role: "assistant",

    text:
      response +
      (applyToAll ? " Scope: all selected clips." : "")
  });

  saveState();

  if (editorTab === "chat") {
    renderChatTab();
  }

  updatePreview();
}

/* Captions */

function renderCaptionsTab() {
  const settings = getSettings();

  $("#editor-tab-body").innerHTML = `
    <h3>Words that stay with you.</h3>

    <label>
      <input
        id="captions-enabled"
        type="checkbox"
        ${settings.caption ? "checked" : ""}
      >
      Show captions
    </label>

    <label for="caption-preset">
      Caption preset
    </label>

    <select id="caption-preset">
      <option>Choose preset</option>
      <option>Minimal</option>
      <option>Bold yellow</option>
      <option>Cinematic</option>
    </select>

    <div class="two">
      <div>
        <label for="caption-font">Font</label>

        <select id="caption-font">
          ${["Arial", "Georgia", "Verdana", "monospace"]
            .map(font => `
              <option
                ${settings.font === font ? "selected" : ""}
              >
                ${font}
              </option>
            `).join("")}
        </select>
      </div>

      <div>
        <label for="caption-size">Size</label>

        <input
          id="caption-size"
          type="number"
          min="10"
          max="60"
          value="${settings.size}"
        >
      </div>

      <div>
        <label for="caption-color">
          Text color
        </label>

        <input
          id="caption-color"
          type="color"
          value="${settings.color}"
        >
      </div>

      <div>
        <label for="caption-background">
          Background
        </label>

        <input
          id="caption-background"
          type="color"
          value="${settings.captionBg}"
        >
      </div>
    </div>

    <label for="caption-placement">
      Placement
    </label>

    <select id="caption-placement">
      ${["bottom", "middle", "top"].map(value => `
        <option
          ${settings.placement === value ? "selected" : ""}
        >
          ${value}
        </option>
      `).join("")}
    </select>

    <label for="caption-alignment">
      Alignment
    </label>

    <select id="caption-alignment">
      ${["center", "left", "right"].map(value => `
        <option
          ${settings.align === value ? "selected" : ""}
        >
          ${value}
        </option>
      `).join("")}
    </select>

    <label>
      <input
        id="caption-highlight"
        type="checkbox"
        ${settings.highlight ? "checked" : ""}
      >
      Highlight current word
    </label>

    <small>
      Press Enter in caption text for a line break.
      Captions appear during sample speech intervals.
    </small>

    ${settings.captions.map((caption, index) => `
      <div class="caption-item">
        <button data-caption-seek="${index}">
          ▶ ${timestamp(caption.start)}–${timestamp(
            caption.end
          )}
        </button>

        <textarea
          data-caption-text="${index}"
          aria-label="Caption ${index + 1}"
        >${escapeHTML(caption.text)}</textarea>

        <div class="two">
          <div>
            <label>Start</label>

            <input
              type="number"
              min="0"
              data-caption-index="${index}"
              data-caption-field="start"
              value="${caption.start}"
              aria-label="Caption ${index + 1} start"
            >
          </div>

          <div>
            <label>End</label>

            <input
              type="number"
              min="0"
              data-caption-index="${index}"
              data-caption-field="end"
              value="${caption.end}"
              aria-label="Caption ${index + 1} end"
            >
          </div>
        </div>
      </div>
    `).join("")}
  `;

  bindSetting("captions-enabled", "caption");

  bindSetting("caption-font", "font");

  bindSetting(
    "caption-size",
    "size",
    value => Math.max(10, Math.min(60, Number(value)))
  );

  bindSetting("caption-color", "color");

  bindSetting("caption-background", "captionBg");

  bindSetting("caption-placement", "placement");

  bindSetting("caption-alignment", "align");

  bindSetting("caption-highlight", "highlight");

  $("#caption-preset").onchange = event => {
    const preset = event.target.value;

    if (preset === "Choose preset") return;

    updateSettings(settings => {
      settings.caption = true;

      settings.size = preset === "Minimal" ? 18 : 28;

      settings.color = preset === "Bold yellow"
        ? "#ffdd33"
        : "#ffffff";

      settings.font = preset === "Cinematic"
        ? "Georgia"
        : "Arial";
    });
  };

  $$("[data-caption-text]").forEach(input => {
    input.onchange = () => {
      const index = Number(input.dataset.captionText);

      updateSettings(settings => {
        settings.captions[index].text = input.value;
      });
    };
  });

  $$("[data-caption-field]").forEach(input => {
    input.onchange = () => {
      const index = Number(input.dataset.captionIndex);

      const field = input.dataset.captionField;

      const value = Number(input.value);

      const caption = getSettings().captions[index];

      const invalid =
        value < 0 ||
        (field === "start" && value >= caption.end) ||
        (field === "end" && value <= caption.start);

      if (invalid) {
        showToast(
          "Caption end must be after its start."
        );

        renderCaptionsTab();

        return;
      }

      updateSettings(settings => {
        settings.captions[index][field] = value;
      });
    };
  });

  $$("[data-caption-seek]").forEach(button => {
    button.onclick = () => {
      const index = Number(button.dataset.captionSeek);

      const settings = getSettings();

      currentTime = Math.max(
        0,
        settings.captions[index].start -
          settings.trimStart
      );

      updatePreview();
    };
  });
}

/* Aspect ratio */

function renderRatioTab() {
  const settings = getSettings();

  $("#editor-tab-body").innerHTML = `
    <h3>A frame for every story.</h3>

    <div
      class="grid"
      style="grid-template-columns: 1fr 1fr;"
    >
      ${[
        ["9:16", "Phone / Reels"],
        ["16:9", "Desktop / YouTube"],
        ["1:1", "Square"],
        ["4:5", "Social feed"],
        ["4:3", "iPad / classic"]
      ].map(([ratio, label]) => `
        <button
          data-ratio="${ratio}"
          class="${settings.ratio === ratio ? "primary" : ""}"
        >
          ${ratio}<br>${label}
        </button>
      `).join("")}
    </div>

    <label for="framing-mode">
      Framing
    </label>

    <select id="framing-mode">
      <option
        value="crop"
        ${settings.fit === "crop" ? "selected" : ""}
      >
        Crop to fill
      </option>

      <option
        value="fit"
        ${settings.fit === "fit" ? "selected" : ""}
      >
        Fit whole video
      </option>
    </select>

    <label for="position-x">
      Horizontal position
    </label>

    <input
      id="position-x"
      type="range"
      min="0"
      max="100"
      value="${settings.x}"
    >

    <label for="position-y">
      Vertical position
    </label>

    <input
      id="position-y"
      type="range"
      min="0"
      max="100"
      value="${settings.y}"
    >

    <label for="frame-scale">
      Scale
    </label>

    <input
      id="frame-scale"
      type="range"
      min="50"
      max="180"
      value="${settings.scale}"
    >

    <label for="frame-background">
      Fit background
    </label>

    <input
      id="frame-background"
      type="color"
      value="${settings.bg}"
    >

    <label>
      <input
        id="safe-area"
        type="checkbox"
        ${settings.safe ? "checked" : ""}
      >
      Show safe area
    </label>

    <button
      id="center-subject"
      style="margin-top: 18px;"
    >
      Keep subject centered (demo)
    </button>
  `;

  $$("[data-ratio]").forEach(button => {
    button.onclick = () => {
      updateSettings(settings => {
        settings.ratio = button.dataset.ratio;
      });
    };
  });

  bindSetting("framing-mode", "fit");

  bindSetting("position-x", "x", Number);

  bindSetting("position-y", "y", Number);

  bindSetting("frame-scale", "scale", Number);

  bindSetting("frame-background", "bg");

  bindSetting("safe-area", "safe");

  $("#center-subject").onclick = () => {
    updateSettings(settings => {
      settings.x = 50;
      settings.y = 50;
    });

    showToast(
      "Position centered. Subject tracking is simulated."
    );
  };
}

/* B-roll */

function renderBrollTab() {
  const settings = getSettings();

  $("#editor-tab-body").innerHTML = `
    <h3>Give the story another layer.</h3>

    <div class="tabs">
      <button id="broll-library">
        Library
      </button>

      <button id="broll-uploaded">
        Uploaded
      </button>

      <button id="broll-ai">
        AI generated
      </button>
    </div>

    <label for="broll-upload">
      Upload image / video
    </label>

    <input
      id="broll-upload"
      type="file"
      accept="image/*,video/*"
    >

    <label for="broll-prompt">
      Generate B-roll (simulated)
    </label>

    <input
      id="broll-prompt"
      placeholder="Mist moving through a forest…"
    >

    <button
      id="generate-broll"
      style="margin-top: 10px;"
    >
      Generate candidates
    </button>

    <div id="broll-assets">
      ${[
        "Forest canopy",
        "Waterfall detail",
        "Quiet workspace"
      ].map(name => `
        <div class="asset">
          ${thumbnail(name)}

          <button
            data-add-broll="${name}"
            style="margin-top: 10px;"
          >
            ＋ Add to timeline
          </button>
        </div>
      `).join("")}
    </div>

    ${settings.broll.map((asset, index) => `
      <div class="asset">
        <b>${escapeHTML(asset.name)}</b>

        <small>
          · ${escapeHTML(asset.category)}
        </small>

        <div class="two">
          <div>
            <label>Start (s)</label>

            <input
              type="number"
              min="0"
              value="${asset.start}"
              data-asset-index="${index}"
              data-asset-field="start"
              aria-label="B-roll start"
            >
          </div>

          <div>
            <label>Duration (s)</label>

            <input
              type="number"
              min="1"
              value="${asset.duration}"
              data-asset-index="${index}"
              data-asset-field="duration"
              aria-label="B-roll duration"
            >
          </div>
        </div>

        <label>Display mode</label>

        <select
          data-asset-index="${index}"
          data-asset-field="mode"
          aria-label="B-roll display mode"
        >
          <option
            ${asset.mode === "Picture in picture"
              ? "selected"
              : ""}
          >
            Picture in picture
          </option>

          <option
            ${asset.mode === "Full frame"
              ? "selected"
              : ""}
          >
            Full frame
          </option>
        </select>

        <label>Position</label>

        <select
          data-asset-index="${index}"
          data-asset-field="position"
          aria-label="B-roll position"
        >
          <option
            ${asset.position === "Top right"
              ? "selected"
              : ""}
          >
            Top right
          </option>

          <option
            ${asset.position === "Bottom left"
              ? "selected"
              : ""}
          >
            Bottom left
          </option>
        </select>

        <label>Scale (%)</label>

        <input
          type="range"
          min="15"
          max="80"
          value="${asset.scale}"
          data-asset-index="${index}"
          data-asset-field="scale"
          aria-label="B-roll scale"
        >

        <label>
          <input
            type="checkbox"
            data-asset-index="${index}"
            data-asset-field="audio"
            ${asset.audio ? "checked" : ""}
          >
          Asset audio (simulated)
        </label>

        <button
          data-remove-broll="${index}"
          style="margin-top: 12px;"
        >
          Remove asset
        </button>
      </div>
    `).join("")}
  `;

  bindBrollCandidates();

  $("#broll-upload").onchange = event => {
    const file = event.target.files[0];

    if (!file) return;

    addBroll(file.name, "Uploaded placeholder");
  };

  $("#generate-broll").onclick = () => {
    const prompt =
      $("#broll-prompt").value.trim() || "Forest mist";

    $("#broll-assets").innerHTML =
      ["Wide view", "Close detail"].map(label => `
        <div class="asset">
          ${thumbnail(label)}

          <small>
            Simulated AI candidate:
            ${escapeHTML(prompt)}
          </small>

          <button
            data-add-broll="${escapeHTML(
              `${label}: ${prompt}`
            )}"
          >
            Add to timeline
          </button>
        </div>
      `).join("");

    bindBrollCandidates();
  };

  $("#broll-library").onclick = renderBrollTab;

  $("#broll-uploaded").onclick = () => {
    showToast(
      "Uploaded assets are listed below as placeholder overlays."
    );
  };

  $("#broll-ai").onclick = () => {
    $("#broll-prompt").focus();
  };

  $$("[data-remove-broll]").forEach(button => {
    button.onclick = () => {
      const index = Number(button.dataset.removeBroll);

      updateSettings(settings => {
        settings.broll.splice(index, 1);
      });
    };
  });

  $$("[data-asset-field]").forEach(input => {
    input.onchange = () => {
      const index = Number(input.dataset.assetIndex);

      const field = input.dataset.assetField;

      let value = input.value;

      if (input.type === "checkbox") {
        value = input.checked;
      } else if (
        ["start", "duration", "scale"].includes(field)
      ) {
        value = Math.max(
          field === "duration" ? 1 : 0,
          Number(value)
        );
      }

      updateSettings(settings => {
        settings.broll[index][field] = value;
      });
    };
  });
}

function bindBrollCandidates() {
  $$("[data-add-broll]").forEach(button => {
    button.onclick = () => {
      addBroll(
        button.dataset.addBroll,
        "Sample / simulated asset"
      );
    };
  });
}

function addBroll(name, category) {
  currentTime = 0;

  updateSettings(settings => {
    settings.broll.push({
      name,
      category,
      start: 0,
      duration: 5,
      mode: "Picture in picture",
      position: "Top right",
      scale: 35,
      audio: false
    });
  });

  showToast(
    "Placeholder B-roll added to the timeline."
  );
}

/* Saving and versions */

function saveFinishedClip() {
  const key = editorKey();

  state.finished[key] = {
    projectId: currentProject().id,
    clipId: state.active,
    title: currentClip().title,
    settings: clone(getSettings()),
    status: "Ready",
    saved: Date.now()
  };

  state.versions[key] ??= [];

  state.versions[key].push({
    date: Date.now(),
    settings: clone(getSettings())
  });

  saveState();

  renderEditorWorkspace();

  showToast(
    "Finished demo version saved. Open Exports to review it."
  );
}

function openVersionHistory() {
  const versions = state.versions[editorKey()] || [];

  openModal(
    "Saved versions",
    versions.length
      ? versions.map((version, index) => `
          <div
            class="row between"
            style="margin: 12px 0;"
          >
            <span>
              Version ${index + 1} ·
              ${new Date(
                version.date
              ).toLocaleTimeString()}
            </span>

            <button data-restore-version="${index}">
              Restore
            </button>
          </div>
        `).join("")
      : `
          <p class="muted">
            Save a finished clip to create
            its first version.
          </p>
        `
  );

  $$("[data-restore-version]").forEach(button => {
    button.onclick = () => {
      const index = Number(
        button.dataset.restoreVersion
      );

      updateSettings(settings => {
        Object.assign(
          settings,
          clone(versions[index].settings)
        );
      });

      closeModal();

      showToast("Saved version restored.");
    };
  });
}

function combineClips() {
  openModal(
    "Combine selected clips",
    `
      <p>
        Create a separate combined draft from
        ${state.selected.length} selected clips.
      </p>

      <p class="notice">
        This simulates a sequence.
        It does not concatenate video files.
      </p>
    `,
    () => {
      const project = currentProject();

      const id = `combined${Date.now()}`;

      const duration = state.selected.reduce(
        (total, clipId) => {
          const settings = getSettings(clipId);

          return total +
            settings.trimEnd -
            settings.trimStart;
        },
        0
      );

      project.clips[id] = {
        id,
        title: "Combined story",
        start: 0,
        end: duration,
        reason: "Combined demo sequence",
        branch: project.branches[0].id
      };

      project.branches[0].clips.push(id);

      state.settings[`${project.id}:${id}`] = {
        ...defaultSettings(duration),
        segments: state.selected.length
      };

      state.selected.push(id);

      state.active = id;

      currentTime = 0;

      saveState();

      closeModal();

      renderEditorWorkspace();
    },
    "Create combined draft"
  );
}

/* Exports */

function renderExports() {
  $("#app").innerHTML = `
    <div class="container">
      <p class="eyebrow">
        03 / Ready to share
      </p>

      <div class="row between">
        <div>
          <h1>Your finished stories.</h1>

          <p class="muted">
            Review saved versions and explore
            the export workflow.
          </p>
        </div>

        <a
          class="button"
          href="${FILES.canvas}"
        >
          Back to project
        </a>
      </div>

      <div class="card toolbar">
        <div class="row">
          <label>
            <input
              id="select-all-exports"
              type="checkbox"
            >
            Select all
          </label>

          <select
            id="export-resolution"
            style="width: auto;"
            aria-label="Resolution"
          >
            <option>1080p</option>
            <option>720p</option>
            <option>4K</option>
          </select>

          <select
            id="export-format"
            style="width: auto;"
            aria-label="Format"
          >
            <option>MP4</option>
            <option>MOV</option>
          </select>

          <select
            id="export-platform"
            style="width: auto;"
            aria-label="Platform preset"
          >
            <option>Custom</option>
            <option>TikTok / Reels</option>
            <option>YouTube</option>
          </select>

          <button
            id="export-selected"
            class="primary"
          >
            Export selected (demo)
          </button>
        </div>

        <div class="row">
          <label>
            <input
              id="export-burn-captions"
              type="checkbox"
              checked
            >
            Burned-in captions
          </label>

          <label>
            <input
              id="export-caption-file"
              type="checkbox"
            >
            Separate caption file
          </label>

          <label>
            <input
              id="export-failure"
              type="checkbox"
            >
            Simulate export failure
          </label>
        </div>

        <p class="notice">
          No video renderer is connected.
          Downloads contain demo settings and
          optional sample captions, not rendered video.
        </p>
      </div>

      <div
        id="exports-grid"
        class="grid"
      ></div>
    </div>
  `;

  drawExports();

  $("#select-all-exports").onchange = event => {
    $$("[data-export-check]").forEach(input => {
      input.checked = event.target.checked;
    });
  };

  $("#export-selected").onclick = () => {
    const selected = $$("[data-export-check]:checked");

    if (!selected.length) {
      showToast("Select a finished clip first.");

      return;
    }

    selected.forEach(input => {
      simulateExport(input.dataset.exportCheck);
    });
  };

  $("#export-platform").onchange = event => {
    showToast(
      `${event.target.value} preset selected for simulated export.`
    );
  };
}

function drawExports() {
  const selectedBeforeRender = new Set(
    $$("[data-export-check]:checked")
      .map(input => input.dataset.exportCheck)
  );

  const entries = Object.entries(
    state.finished
  ).filter(([, finished]) => {
    return state.projects.some(project => {
      return (
        project.id === finished.projectId &&
        project.clips[finished.clipId]
      );
    });
  });

  $("#exports-grid").innerHTML = entries.length
    ? entries.map(([key, finished]) => {
        const settings = finished.settings;

        const progress = finished.status === "Complete"
          ? 100
          : finished.status === "Rendering"
            ? 65
            : finished.status === "Queued"
              ? 15
              : 0;

        return `
          <article class="card export-card">
            ${thumbnail("▶ Finished sample")}

            <label>
              <input
                type="checkbox"
                data-export-check="${escapeHTML(key)}"
                ${
                  selectedBeforeRender.has(key)
                    ? "checked"
                    : ""
                }
              >
              Select clip
            </label>

            <h3>${escapeHTML(finished.title)}</h3>

            <small>
              ${settings.trimEnd - settings.trimStart}s ·
              ${settings.ratio} ·
              Saved
              ${new Date(
                finished.saved
              ).toLocaleDateString()}
            </small>

            <p class="pill">
              ${escapeHTML(finished.status)}
            </p>

            <div class="progress">
              <i style="width: ${progress}%;"></i>
            </div>

            <div class="row">
              <button
                data-export-preview="${escapeHTML(key)}"
              >
                Preview
              </button>

              <button
                data-edit-finished="${escapeHTML(key)}"
              >
                Edit again
              </button>

              <button
                data-export-one="${escapeHTML(key)}"
                ${
                  ["Queued", "Rendering"].includes(
                    finished.status
                  ) ? "disabled" : ""
                }
              >
                ${
                  finished.status === "Failed"
                    ? "Retry"
                    : "Export"
                }
              </button>

              ${finished.status === "Complete" ? `
                <button
                  class="primary"
                  data-download-demo="${escapeHTML(key)}"
                >
                  Download demo settings
                </button>
              ` : ""}
            </div>

            <div
              class="row"
              style="margin-top: 14px;"
            >
              <button data-social="TikTok">
                TikTok
              </button>

              <button data-social="Instagram">
                Instagram
              </button>

              <button data-social="YouTube">
                YouTube
              </button>
            </div>
          </article>
        `;
      }).join("")
    : `
        <div class="card empty">
          <h3>No finished clips yet.</h3>

          <p class="muted">
            Save a finished clip in the editor
            to see it here.
          </p>

          <a
            class="button"
            href="${FILES.editor}"
          >
            Open editor
          </a>
        </div>
      `;

  $$("[data-edit-finished]").forEach(button => {
    button.onclick = () => {
      const finished =
        state.finished[button.dataset.editFinished];

      state.project = finished.projectId;

      state.active = finished.clipId;

      state.selected = state.selected.filter(id => {
        return Boolean(currentProject().clips[id]);
      });

      if (!state.selected.includes(finished.clipId)) {
        state.selected.push(finished.clipId);
      }

      navigate("editor");
    };
  });

  $$("[data-export-one]").forEach(button => {
    button.onclick = () => {
      simulateExport(button.dataset.exportOne);
    };
  });

  $$("[data-export-preview]").forEach(button => {
    button.onclick = () => {
      const finished =
        state.finished[button.dataset.exportPreview];

      openModal(
        finished.title,
        `
          ${thumbnail("Saved sample preview")}

          <p>
            ${finished.settings.ratio} ·
            ${
              finished.settings.trimEnd -
              finished.settings.trimStart
            } seconds
          </p>

          <p class="muted">
            Saved caption:
            ${escapeHTML(
              finished.settings.captions[0]?.text ||
              "No captions"
            )}
          </p>

          <p class="notice">
            Illustrative preview of the saved
            demo version.
          </p>
        `
      );
    };
  });

  $$("[data-social]").forEach(button => {
    button.onclick = () => {
      showToast(
        `Demo only: ${button.dataset.social} sharing is not connected.`
      );
    };
  });

  $$("[data-download-demo]").forEach(button => {
    button.onclick = () => {
      const finished =
        state.finished[button.dataset.downloadDemo];

      downloadFile(
        "cascade-demo-settings.json",
        JSON.stringify(
          {
            notice:
              "Prototype settings only. This is not rendered video.",

            ...finished
          },
          null,
          2
        ),
        "application/json"
      );

      if ($("#export-caption-file").checked) {
        downloadFile(
          "sample-captions.vtt",
          buildCaptionFile(finished.settings),
          "text/vtt"
        );
      }
    };
  });
}

async function simulateExport(key) {
  const finished = state.finished[key];

  if (
    ["Queued", "Rendering"].includes(finished.status)
  ) {
    return;
  }

  const fail = $("#export-failure").checked;

  finished.options = {
    resolution: $("#export-resolution").value,
    format: $("#export-format").value,
    platform: $("#export-platform").value,
    burnedInCaptions: $("#export-burn-captions").checked
  };

  for (const status of [
    "Queued",
    "Rendering",
    fail ? "Failed" : "Complete"
  ]) {
    finished.status = status;

    saveState();

    drawExports();

    await wait(550);
  }

  showToast(
    fail
      ? "Simulated failure. Turn off the failure checkbox and retry."
      : "Demo export complete. Settings are available to download."
  );
}

/* Demo downloads */

function vttTimestamp(seconds) {
  const totalMilliseconds =
    Math.round(Math.max(0, seconds) * 1000);

  const hours = Math.floor(
    totalMilliseconds / 3600000
  );

  const minutes = Math.floor(
    totalMilliseconds % 3600000 / 60000
  );

  const wholeSeconds = Math.floor(
    totalMilliseconds % 60000 / 1000
  );

  const milliseconds = totalMilliseconds % 1000;

  return (
    String(hours).padStart(2, "0") + ":" +
    String(minutes).padStart(2, "0") + ":" +
    String(wholeSeconds).padStart(2, "0") + "." +
    String(milliseconds).padStart(3, "0")
  );
}

function buildCaptionFile(settings) {
  if (!settings.caption) {
    return "WEBVTT\n\n";
  }

  const captions = settings.captions
    .filter(caption => {
      return (
        caption.end > settings.trimStart &&
        caption.start < settings.trimEnd
      );
    })
    .map((caption, index) => {
      const start = Math.max(
        0,
        caption.start - settings.trimStart
      );

      const end =
        Math.min(caption.end, settings.trimEnd) -
        settings.trimStart;

      return (
        `${index + 1}\n` +
        `${vttTimestamp(start)} --> ` +
        `${vttTimestamp(end)}\n` +
        caption.text
      );
    });

  return "WEBVTT\n\n" + captions.join("\n\n") + "\n";
}

function downloadFile(filename, content, mimeType) {
  const blob = new Blob(
    [content],
    { type: mimeType }
  );

  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");

  link.href = url;

  link.download = filename;

  document.body.appendChild(link);

  link.click();

  link.remove();

  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 1000);
}

/* Start the current page */

renderHeader();

const pageRenderers = {
  index: renderLanding,
  login: renderLogin,
  projects: renderProjects,
  canvas: renderCanvas,
  editor: renderEditor,
  exports: renderExports
};

const renderPage =
  pageRenderers[page] || renderLanding;

renderPage();