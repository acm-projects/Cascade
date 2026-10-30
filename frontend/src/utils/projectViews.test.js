import test from "node:test";
import assert from "node:assert/strict";
import { deleteTrashedProjects, isTrashed, projectMatchesView } from "./projectViews.js";

const now = 2000000;
const fresh = { created_at: now - 60, favorite: false, archived: false, trashed_at: null };
const views = ["all", "recent", "favorites", "archives", "trash"];
const matches = (project) => views.filter((view) => projectMatchesView(project, view, now));

test("old records default to active; recent honors the existing seven-day window", () => {
  assert.deepEqual(matches({ created_at: now - 60 }), ["all", "recent"]);
  assert.deepEqual(matches({ created_at: now - 8 * 86400 }), ["all"]);
  assert.deepEqual(matches({ created_at: 1, updated_at: now - 60 }), ["all", "recent"]);
});

test("archive and trash exclusions hold across all five views", () => {
  assert.deepEqual(matches({ ...fresh, favorite: true }), ["all", "recent", "favorites"]);
  assert.deepEqual(matches({ ...fresh, favorite: true, archived: true }), ["favorites", "archives"]);
  assert.deepEqual(matches({ ...fresh, favorite: true, archived: true, trashed_at: now }), ["trash"]);
  assert.equal(isTrashed({ trashed_at: 0 }), true);
});

test("restoring returns to the saved favorite/archive state", () => {
  const trashed = { ...fresh, favorite: true, archived: true, trashed_at: now };
  assert.deepEqual(matches({ ...trashed, trashed_at: null }), ["favorites", "archives"]);
  assert.deepEqual(matches({ ...trashed, trashed_at: null, archived: false }), ["all", "recent", "favorites"]);
});


test("empty trash deletes only trashed projects and retains failed deletes", async () => {
  const projects = [
    { id: "active", name: "Active", trashed_at: null },
    { id: "blocked", name: "Blocked", trashed_at: now },
    { id: "deleted", name: "Deleted", trashed_at: now },
    { id: "archived", name: "Archived", archived: true },
  ];
  const called = [];
  const result = await deleteTrashedProjects(projects, async (id) => {
    called.push(id);
    if (id === "blocked") throw new Error("Stop active generation first.");
  });
  assert.deepEqual(called, ["blocked", "deleted"]);
  assert.deepEqual([...result.removed], ["deleted"]);
  assert.deepEqual(result.failures, ["Blocked: Stop active generation first."]);
});

test("empty trash with no trashed projects makes no delete requests", async () => {
  const result = await deleteTrashedProjects([fresh], () => assert.fail("unexpected delete"));
  assert.equal(result.removed.size, 0);
  assert.deepEqual(result.failures, []);
});
