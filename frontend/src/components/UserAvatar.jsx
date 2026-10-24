import { Link } from "react-router-dom";
import { SignedIn, SignedOut, UserButton } from "@clerk/clerk-react";
import { useAuthMode } from "../auth/AuthContext";
import "./UserAvatar.css";

// The round account button at the right of the top bars.
// Clerk mode: Clerk's account button (sign out, manage account), or a sign-in link when signed out.
// Dev mode: a green "D" circle.
//   className - extra class for size/position (e.g. "topnav-avatar")
function UserAvatar({ className = "" }) {
  const mode = useAuthMode();
  const classes = `user-avatar ${className}`;

  if (mode === "clerk") {
    return (
      <>
        <SignedIn>
          <span className={classes}>
            <UserButton appearance={{ elements: { avatarBox: { width: "100%", height: "100%" } } }} />
          </span>
        </SignedIn>
        <SignedOut>
          <Link to="/sign-in" className={`${classes} user-avatar-letter`} title="Sign in">?</Link>
        </SignedOut>
      </>
    );
  }
  return (
    <span className={`${classes} user-avatar-letter`} title="Dev mode: not signed in">D</span>
  );
}

export default UserAvatar;
