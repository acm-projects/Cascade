// Turn seconds into "m:ss", e.g. 75 -> "1:15"
export function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// Turn a time into words: "just now", "5 minutes ago", "2 hours ago", "3 days ago", then a date.
// timestampSeconds is in seconds (like the backend's created_at), not milliseconds.
export function timeAgo(timestampSeconds, now = Date.now()) {
  const seconds = Math.max(0, Math.floor(now / 1000 - timestampSeconds));
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"} ago`;

  if (seconds < 60) return "just now";
  if (seconds < 3600) return plural(Math.floor(seconds / 60), "minute");
  if (seconds < 86400) return plural(Math.floor(seconds / 3600), "hour");
  if (seconds < 7 * 86400) return plural(Math.floor(seconds / 86400), "day");
  return new Date(timestampSeconds * 1000).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
