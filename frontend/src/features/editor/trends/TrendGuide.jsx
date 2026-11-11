import Capybara from '../../../components/Capybara';

// Cascade's capybara walks the user through the analysis: a mascot with a speech bubble.
//   big  - the full, idling capybara (top of the window); otherwise just its head (beside each step)
export default function Guide({ children, big = false, tone = 'info', live = false }) {
  return <div className={`ta-guide${big ? ' ta-guide-big' : ''} ta-guide-${tone}`}>
    <span className="ta-guide-mascot">{big ? <Capybara variant="full" size={170} /> : <Capybara variant="head" size={52} />}</span>
    <p className="ta-bubble" role={live ? 'status' : undefined}>{children}</p>
  </div>;
}

/** A numbered step heading with the guide's one-line introduction. */
export function Step({ number, title, children, id }) {
  return <header className="ta-step-head">
    <span className="ta-step-no" aria-hidden="true">{number}</span>
    <div><small className="ta-eyebrow">Step {number}</small><h2 id={id}>{title}</h2></div>
    {children && <Guide>{children}</Guide>}
  </header>;
}
