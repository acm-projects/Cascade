// Optimistic concurrency: an AI response never silently overwrites newer manual edits.
export const sameEdit = (left, right) => JSON.stringify(left) === JSON.stringify(right);
export const isAIUndo = text => /^\s*(?:please\s+)?undo (?:your|the last ai|my last ai|last ai)(?: last)? edit[.!]?\s*$/i.test(text);
export function canUndoAI(transaction, state) {
  return !!transaction && sameEdit(transaction.after, state);
}
