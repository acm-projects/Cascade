import { Link } from "react-router-dom";
import { SignedIn, SignedOut, UserButton, useUser } from "@clerk/clerk-react";
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

// The signed-in person's name, for the top bar next to the avatar.
function ClerkName({ className }) {
  const { user } = useUser();
  const name = user?.fullName || user?.firstName || user?.username || user?.primaryEmailAddress?.emailAddress;
  return name ? <span className={className} title={name}>{name}</span> : null;
}

//   className - extra class for size/position (e.g. "topnav-user")
export function UserName({ className = "" }) {
  const mode = useAuthMode();
  if (mode === "clerk") return <SignedIn><ClerkName className={className} /></SignedIn>;
  return <span className={className}>Dev user</span>;
}
