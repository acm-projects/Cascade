import "./JungleLeaves.css";
import background from "../assets/test/fog-layers/fog-plate.webp";
import topLeft from "../assets/test/fog-layers/fog-topleft.webp";
import lowLeft from "../assets/test/fog-layers/fog-lowleft.webp";
import topRight from "../assets/test/fog-layers/fog-topright.webp";
import vine1 from "../assets/test/fog-layers/fog-vine1.webp";
import vine2 from "../assets/test/fog-layers/fog-vine2.webp";
import bottomLeft from "../assets/test/fog-layers/fog-bottomleft.webp";
import bottomRight from "../assets/test/fog-layers/fog-bottomright.webp";

const layers = [
  { name: "topleft", src: topLeft },
  { name: "lowleft", src: lowLeft },
  { name: "topright", src: topRight },
  { name: "vine1", src: vine1 },
  { name: "vine2", src: vine2 },
  { name: "bottomleft", src: bottomLeft },
  { name: "bottomright", src: bottomRight },
];

// The foggy jungle picture, split into layers so its front leaves can sway (see JungleLeaves.css).
// Goes behind everything else on the page.
function JungleLeaves() {
  return (
    <div className="jungle-scene" style={{ backgroundImage: `url(${background})` }} aria-hidden="true">
      {layers.map((layer) => (
        <img key={layer.name} className={`jungle-leaves jungle-leaves-${layer.name}`} src={layer.src} alt="" />
      ))}
    </div>
  );
}

export default JungleLeaves;
