import Button from "./Button";
import "./ui.css";

// "Nothing here yet" message, with an optional button.
//   <EmptyState icon="🎬" title="No projects yet" text="Make your first one!"
//               action={{ label: "+ New Project", onClick: handleNew }} />
function EmptyState({ icon = "🌿", title, text, action }) {
  return (
    <div className="ui-empty">
      <span className="ui-empty-icon" aria-hidden="true">{icon}</span>
      <h3 className="ui-empty-title">{title}</h3>
      {text && <p className="ui-empty-text">{text}</p>}
      {action && (
        <Button variant="primary" size="sm" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}

export default EmptyState;
