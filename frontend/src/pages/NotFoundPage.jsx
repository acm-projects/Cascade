import { Link, useLocation } from "react-router-dom";
import "./NotFoundPage.css";

// Shown for any URL that isn't in App.jsx
function NotFoundPage() {
  const { pathname } = useLocation();

  return (
    <div className="not-found leaf-page">
      <div className="not-found-card">
        <p className="not-found-code">404</p>
        <h1 className="not-found-title">Lost in the jungle 🌴</h1>
        <p className="not-found-text">
          There's no trail at <code>{pathname}</code>.
        </p>
        <Link to="/projects" className="btn btn-primary">
          Back to my projects
        </Link>
      </div>
    </div>
  );
}

export default NotFoundPage;
