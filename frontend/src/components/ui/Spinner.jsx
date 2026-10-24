import "./ui.css";

// A spinning circle for "loading...".
//   <Spinner />   <Spinner size={16} label="Saving" />
function Spinner({ size = 32, label = "Loading" }) {
  return <span className="ui-spinner" role="status" aria-label={label} style={{ "--spinner-size": `${size}px` }} />;
}

export default Spinner;
