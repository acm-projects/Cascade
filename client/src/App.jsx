import Landing from "./pages/Landing";
import LandingVideo from "./pages/LandingVideo";
import BlimpSection from "./pages/BlimpSection";
import Login from "./pages/Login";
import River from "./pages/River";

const USE_VIDEO = false;   // ← flip to true to see the video version

function App() {
  return (
    <div className="sky">
      {USE_VIDEO ? <LandingVideo /> : <Landing />}
      <BlimpSection />
      <Login />
      <River />
    </div>
  );
}

export default App;
