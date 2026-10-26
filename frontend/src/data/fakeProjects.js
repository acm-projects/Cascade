// FAKE projects until the backend can send real ones.
// Each has a few clips (start/end seconds) so the editor has something to show.
// No real video file exists for these, so the editor shows a placeholder instead of video.
const fakeProjects = [
  { id: "p1", name: "My First Video", edited: "2 hours ago", favorite: true, archived: false, trashed: false,
    clips: [{ id: 0, start: 5, end: 11 }, { id: 1, start: 17, end: 24 }, { id: 2, start: 62, end: 70 }] },
  { id: "p2", name: "Travel Vlog", edited: "3 days ago", favorite: false, archived: false, trashed: false,
    clips: [{ id: 0, start: 0, end: 6 }, { id: 1, start: 12, end: 20 }] },
  { id: "p3", name: "Podcast Highlights", edited: "1 week ago", favorite: true, archived: false, trashed: false,
    clips: [{ id: 0, start: 30, end: 45 }] },
  { id: "p4", name: "Test Project", edited: "2 weeks ago", favorite: false, archived: true, trashed: false,
    clips: [{ id: 0, start: 2, end: 9 }, { id: 1, start: 14, end: 18 }] },
  { id: "p5", name: "Interview Edits", edited: "1 month ago", favorite: false, archived: false, trashed: false,
    clips: [{ id: 0, start: 10, end: 16 }, { id: 1, start: 40, end: 48 }, { id: 2, start: 75, end: 81 }] },
  { id: "p6", name: "Old Draft", edited: "2 months ago", favorite: false, archived: false, trashed: true,
    clips: [{ id: 0, start: 0, end: 5 }] },
];

export default fakeProjects;
