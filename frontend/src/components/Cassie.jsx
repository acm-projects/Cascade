import Mascot from "./Mascot";
import Seahorse from "./Seahorse";

// Cassie, Cascade's mascot: in the corner of the Projects page and next to the AI Studio chat.
// She's the Director frog right now (Mascot.jsx, made in frontend/blender/frog_director.py). She used to be a
// seahorse (Seahorse.jsx, frontend/blender/seahorse.py), which is kept in case Sai wants her back:
// to switch, change CASSIE_IS to "seahorse".
//   variant="full" - all of her, animated
//   variant="head" - a still picture of her face, for small round badges
//   size           - width in pixels
const CASSIE_IS = "frog";

function Cassie(props) {
  return CASSIE_IS === "seahorse" ? <Seahorse {...props} /> : <Mascot {...props} />;
}

export default Cassie;
