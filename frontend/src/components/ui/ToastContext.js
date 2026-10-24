import { createContext, useContext } from "react";

export const ToastContext = createContext({ show: () => {} });

// Pop up a little message that disappears by itself:
//   const toast = useToast();
//   toast.show("Saved!");               // green
//   toast.show("Upload failed", "error"); // red
export function useToast() {
  return useContext(ToastContext);
}
