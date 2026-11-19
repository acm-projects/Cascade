// Demo: the frog sitting on the Trends button types this into the AI Editor chat. It describes the saved demo edit.
export const DEMO_EDIT_PROMPT = "Make a 13-second cinematic jaguar edit: hook on “as close to him as I am to you”, fast cuts with jaguar b-roll, big keyword text (AS CLOSE, DIDN’T CARE, AMAZON, ATTACKED, 20, TEETH), orange then red, black-and-white mixed with color, impact hits, and a dramatic score.";

export const TYPE_PROMPT = "cascade:type-prompt";
let waiting = null;   // a prompt sent before the chat box was on screen (it picks it up when it opens)

export function typeIntoAIChat(text) {
  waiting = text;
  window.dispatchEvent(new CustomEvent(TYPE_PROMPT, { detail: text }));
}

export function takeWaitingPrompt() {
  const text = waiting;
  waiting = null;
  return text;
}
