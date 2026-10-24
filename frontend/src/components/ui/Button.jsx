import { Link } from "react-router-dom";
import "./ui.css";

const variantClass = {
  primary: "btn-primary", // green wood: the main action on a page
  secondary: "",          // cream wood (plain .btn)
  ghost: "btn-ghost",     // no background: small, quiet actions
};

// The app's button. Uses the .btn styles from theme.css.
//   <Button variant="primary" onClick={save}>Save</Button>
//   <Button size="sm" to="/projects">Back</Button>     (with "to" it's a link)
//   variant: "primary" | "secondary" | "ghost"    size: "sm" | "md"
// Anything else (onClick, disabled, title, ...) is passed straight to the <button>.
function Button({ variant = "secondary", size = "md", to, className = "", type = "button", ...rest }) {
  const classes = ["btn", variantClass[variant], size === "sm" ? "btn-small" : "btn-md", className]
    .filter(Boolean)
    .join(" ");

  if (to) {
    return <Link to={to} className={classes} {...rest} />;
  }
  return <button type={type} className={classes} {...rest} />;
}

export default Button;
