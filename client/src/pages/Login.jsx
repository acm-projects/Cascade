import { useState } from "react";
import "./Login.css";
import background from "../assets/login-bg.png";
import sign from "../assets/wood-sign.png";

function Login() {
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

  return (
    <div className="login" style={{ backgroundImage: `url(${background})` }}>
      <div className="login-sign" style={{ backgroundImage: `url(${sign})` }}>
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
        </form>

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
        </form>

        {message && <p className="login-message">{message}</p>}
      </div>
    </div>
  );
}

export default Login;