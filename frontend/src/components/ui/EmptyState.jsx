import Button from "./Button";
import "./ui.css";
import Icon from "./Icon";

// "Nothing here yet" message, with an optional button. icon = a name from Icon.jsx.
//   <EmptyState icon="film" title="No projects yet" text="Make your first one!"
//               action={{ label: "+ New Project", onClick: handleNew }} />
function EmptyState({ icon = "leaf", title, text, action }) {
  return (
    <div className="ui-empty">
      <span className="ui-empty-icon" aria-hidden="true"><Icon name={icon} /></span>
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
