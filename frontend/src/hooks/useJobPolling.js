import { useCallback, useEffect, useRef, useState } from "react";

// Watches a slow backend job (clip generation, research, ...) until it finishes.
// The backend answers right away with a job_id; this asks "ready yet?" every intervalMs.
//
//   const api = useApi();
//   const job = useJobPolling(api.getJob);           // or api.getFeature for research jobs
//   const { job_id } = await api.createGeneration(...);
//   job.start(job_id);
//   job.status  -> "idle" | "polling" | "done" | "error" | "stopped"
//   job.data    -> the latest answer, e.g. { state: "processing", message: "Finding clips...", clips: [] }
//   job.error   -> what went wrong when status is "error"
//
// It stops by itself when the job is done or failed, when you call stop(), and when the page closes.
export default function useJobPolling(fetchStatus, { intervalMs = 1500 } = {}) {
  const [status, setStatus] = useState("idle");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const timerRef = useRef(null);
  const runRef = useRef(0); // goes up on every start/stop, so a late answer about an old job is ignored
  const fetchRef = useRef(fetchStatus);

  // Always call the newest fetchStatus without restarting the polling
  useEffect(() => {
    fetchRef.current = fetchStatus;
  });

  const start = useCallback(
    (jobId) => {
      clearTimeout(timerRef.current);
      const run = ++runRef.current;
      setStatus("polling");
      setData(null);
      setError(null);

      async function check() {
        try {
          const result = await fetchRef.current(jobId);
          if (run !== runRef.current) return; // stopped or restarted while we were waiting
          setData(result);
          if (result?.state === "done") {
            setStatus("done");
            return;
          }
          if (result?.state === "error") {
            setError(new Error(result.message ?? "The job failed."));
            setStatus("error");
            return;
          }
        } catch (err) {
          if (run !== runRef.current) return;
          setError(err);
          setStatus("error");
          return;
        }
        // Wait, then ask again. (setTimeout after each answer, not setInterval,
        // so a slow answer never piles up a second request behind it.)
        timerRef.current = setTimeout(check, intervalMs);
      }

      check();
    },
    [intervalMs]
  );

  const stop = useCallback(() => {
    runRef.current += 1;
    clearTimeout(timerRef.current);
    setStatus((current) => (current === "polling" ? "stopped" : current));
  }, []);

  // When the component using this hook disappears (you leave the page), stop asking
  useEffect(() => {
    return () => {
      runRef.current += 1;
      clearTimeout(timerRef.current);
    };
  }, []);

  return { status, data, error, start, stop };
}
