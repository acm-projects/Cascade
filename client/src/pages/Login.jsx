import { useState } from "react";
import "./Login.css";
import tree from "../assets/tree.png";

function Login() {
  const [choice, setChoice] = useState(null); // null, "login", or "signup"
  const [name, setName] = useState("");
  const [signupEmail, setSignupEmail] = useState("");
  const [loginEmail, setLoginEmail] = useState("");
  const [message, setMessage] = useState("");

  function handleSignUp(e) {
    e.preventDefault();
    setMessage(`Signing up ${name} (${signupEmail})`);
  }

  function handleLogin(e) {
    e.preventDefault();
    setMessage(`Logging in ${loginEmail}`);
  }

  function goBack() {
    setChoice(null);
    setMessage("");
  }

  return (
    <div className="login">
      <div className="tree-wrap">
        <img src={tree} alt="" className="tree-img" />

        {/* Step 1: pick Log In or Sign Up */}
        {choice === null && (
          <>
            <button className="tree-btn tree-btn-login" onClick={() => setChoice("login")}>
              Log In
            </button>
            <button className="tree-btn tree-btn-signup" onClick={() => setChoice("signup")}>
              Sign Up
            </button>
          </>
        )}

        {/* Step 2: show the matching form on the leaves */}
        {choice === "signup" && (
          <form className="login-form" onSubmit={handleSignUp}>
            <h2>SIGN UP</h2>
            <input
              placeholder="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
            <input
              type="email"
              placeholder="Email"
              value={signupEmail}
              onChange={(e) => setSignupEmail(e.target.value)}
              required
            />
            <button type="submit">Sign Up</button>
            <button type="button" className="login-back" onClick={goBack}>
              ← Back
            </button>
          </form>
        )}

        {choice === "login" && (
          <form className="login-form" onSubmit={handleLogin}>
            <h2>LOG IN</h2>
            <input
              type="email"
              placeholder="Email"
              value={loginEmail}
              onChange={(e) => setLoginEmail(e.target.value)}
              required
            />
            <button type="submit">Log In</button>
            <button type="button" className="login-back" onClick={goBack}>
              ← Back
            </button>
          </form>
        )}

        {message && <p className="login-message">{message}</p>}
      </div>
    </div>
  );
}

export default Login;