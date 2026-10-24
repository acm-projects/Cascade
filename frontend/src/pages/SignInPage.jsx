import { Navigate } from "react-router-dom";
import { SignIn } from "@clerk/clerk-react";
import { useAuthMode } from "../auth/AuthContext";
import "./SignInPage.css";
import background from "../assets/figma/landing-bg.jpg";

// /sign-in: Clerk's ready-made sign-in box on the lake background.
// In dev mode there's nothing to sign in to, so it skips straight to your projects.
function SignInPage() {
  const mode = useAuthMode();

  if (mode !== "clerk") {
    return <Navigate to="/projects" replace />;
  }

  return (
    <div className="sign-in" style={{ backgroundImage: `url(${background})` }}>
      <SignIn routing="path" path="/sign-in" fallbackRedirectUrl="/projects" />
    </div>
  );
}

export default SignInPage;
