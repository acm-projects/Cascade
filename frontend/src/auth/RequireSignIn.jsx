import { Outlet } from "react-router-dom";
import { RedirectToSignIn, SignedIn, SignedOut } from "@clerk/clerk-react";
import { useAuthMode } from "./AuthContext";

// Put this around routes that need a signed-in user (see App.jsx).
// Dev mode: always lets you in. Clerk mode: signed in -> show the page, signed out -> go to /sign-in.
function RequireSignIn() {
  const mode = useAuthMode();

  if (mode !== "clerk") {
    return <Outlet />;
  }

  return (
    <>
      <SignedIn>
        <Outlet />
      </SignedIn>
      <SignedOut>
        <RedirectToSignIn />
      </SignedOut>
    </>
  );
}

export default RequireSignIn;
