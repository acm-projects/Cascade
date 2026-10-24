import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ClerkProvider, useAuth } from "@clerk/clerk-react";
import { AuthContext } from "./AuthContext";
import { getAuthConfig } from "../api/auth";
import "./AuthGate.css";

const devAuth = { mode: "dev", getToken: async () => null };

// Wraps the whole app. On load it asks the backend how sign-in works (GET /api/auth-config):
//   { dev_auth: true }              -> dev mode: everyone gets in, getToken() returns null
//   { publishable_key: "pk_..." }   -> real Clerk sign-in
// If the backend can't answer while you're running `npm run dev`, it falls back to dev mode
// (with a small badge) so you can still work on pages. A real build never does that.
function AuthGate({ children }) {
  const [config, setConfig] = useState(null); // null = still asking the backend
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    getAuthConfig()
      .then((data) => !cancelled && setConfig(data))
      .catch((err) => !cancelled && setConfig({ error: err.message }));
    return () => {
      cancelled = true;
    };
  }, []);

  if (!config) {
    return <div className="auth-screen">🌿 Checking the trail…</div>;
  }

  if (config.dev_auth) {
    return (
      <AuthContext.Provider value={devAuth}>
        {children}
        <span className="auth-dev-badge" title="CASCADE_DEV_AUTH is on in the backend">Dev sign-in</span>
      </AuthContext.Provider>
    );
  }

  if (config.publishable_key) {
    return (
      <ClerkProvider
        publishableKey={config.publishable_key}
        signInUrl="/sign-in"
        signInFallbackRedirectUrl="/projects"
        afterSignOutUrl="/"
        // Let Clerk change pages through React Router instead of reloading the whole site
        routerPush={(to) => navigate(to)}
        routerReplace={(to) => navigate(to, { replace: true })}
      >
        <ClerkToken>{children}</ClerkToken>
      </ClerkProvider>
    );
  }

  if (import.meta.env.DEV) {
    return (
      <AuthContext.Provider value={devAuth}>
        {children}
        <span
          className="auth-dev-badge auth-dev-badge-warn"
          title={`Couldn't read /api/auth-config (${config.error ?? "no publishable key"}). Is the backend running?`}
        >
          No backend auth: dev mode
        </span>
      </AuthContext.Provider>
    );
  }

  return (
    <div className="auth-screen">
      Sign-in isn't set up on the server yet ({config.error ?? "no publishable key"}).
    </div>
  );
}

// Lives inside ClerkProvider so it can use Clerk's useAuth() hook, then shares getToken with the app.
function ClerkToken({ children }) {
  const { getToken } = useAuth();
  return <AuthContext.Provider value={{ mode: "clerk", getToken }}>{children}</AuthContext.Provider>;
}

export default AuthGate;
