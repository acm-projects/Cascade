// The small things in the WaterFlow background: rising bubbles, drifting "marine snow", plankton that glows
// brighter the deeper you are, and kelp swaying at the screen edges. (The animals are 3D: seaCreatures.js.)
// It draws on a half-resolution canvas scaled up without smoothing, so every block stays crisp.
//
// getSeaLife(key, canvas) returns { resize(width, height), frame(seconds, dt, depth) }. The same key gets the same
// sea back, so things carry on where they were when you switch between Canvas, Editor and Export.

const between = ([low, high]) => low + Math.random() * (high - low);

function createSea() {
  let canvas = null;
  let ctx = null;
  let W = 1;
  let H = 1;
  let started = false;

  const bubbles = Array.from({ length: 12 }, () => ({}));
  const blow = (bubble, anywhere) => {
    bubble.x = Math.random() * W;
    bubble.y = anywhere ? Math.random() * H : H + Math.random() * H * 0.3;
    bubble.speed = between([10, 22]);
    bubble.r = Math.random() < 0.25 ? between([3, 5]) : between([1, 2.5]);
    bubble.phase = Math.random() * 10;
  };

  // marine snow (pale specks sinking) and plankton (tiny lights that glow brighter the deeper you are)
  const specks = Array.from({ length: 70 }, () => ({ x: Math.random(), y: Math.random(), size: Math.random() < 0.2 ? 2 : 1, speed: between([0.004, 0.012]), phase: Math.random() * 10 }));
  const plankton = Array.from({ length: 36 }, () => ({ x: Math.random(), y: Math.random(), phase: Math.random() * 10, hue: Math.random() < 0.7 ? "120, 255, 228" : "140, 200, 255" }));
  const kelp = [0.008, 0.024, 0.042, 0.958, 0.976, 0.992].map((at) => ({ at, height: between([0.25, 0.5]), phase: Math.random() * 10 }));

  const resize = (width, height) => {
    W = width;
    H = height;
    canvas.width = W;
    canvas.height = H;
    ctx.imageSmoothingEnabled = false;
    if (!started) {
      bubbles.forEach((bubble) => blow(bubble, true));
      started = true;
    } else {
      bubbles.forEach((bubble) => { if (bubble.x > W) bubble.x = Math.random() * W; });
    }
  };

  const drawKelp = (t) => {
    ctx.globalAlpha = 0.85;
    for (const stalk of kelp) {
      const tall = Math.round(H * stalk.height);
      const baseX = Math.round(W * stalk.at);
      for (let i = 0; i < tall; i += 2) {
        const lean = i / tall;
        const x = baseX + Math.round(Math.sin(t * 0.6 + i * 0.05 + stalk.phase) * lean * 6);
        const y = H - 2 - i;
        ctx.fillStyle = (i >> 2) % 3 === 0 ? "#1f4a33" : "#245a3a";
        ctx.fillRect(x, y, 3, 2);
        if (i % 12 === 6) {   // a leaf, alternating sides
          ctx.fillStyle = "#2f6b40";
          ctx.fillRect(i % 24 === 6 ? x - 3 : x + 3, y, 3, 2);
        }
      }
    }
  };

  const frame = (t, dt, depth) => {
    ctx.clearRect(0, 0, W, H);

    // marine snow, very faint, drifting down and sideways
    ctx.fillStyle = "#d8ecff";
    for (const s of specks) {
      s.y += s.speed * dt;
      if (s.y > 1.02) { s.y = -0.02; s.x = Math.random(); }
      ctx.globalAlpha = 0.18 + 0.12 * Math.sin(t + s.phase);
      ctx.fillRect(Math.round(((s.x + Math.sin(t * 0.2 + s.phase) * 0.01) % 1) * W), Math.round(s.y * H), s.size, s.size);
    }

    drawKelp(t);

    // plankton: barely there near the surface, glowing in the deep
    const glow = 0.06 + 0.8 * depth;
    ctx.shadowBlur = 4 + 6 * depth;
    for (const p of plankton) {
      const pulse = 0.5 + 0.5 * Math.sin(t * 0.9 + p.phase);
      const x = Math.round(((p.x + Math.sin(t * 0.05 + p.phase) * 0.03 + 1) % 1) * W);
      const y = Math.round(((p.y + Math.cos(t * 0.04 + p.phase) * 0.03 + 1) % 1) * H);
      ctx.globalAlpha = glow * (0.35 + 0.65 * pulse);
      ctx.shadowColor = `rgb(${p.hue})`;
      ctx.fillStyle = `rgb(${p.hue})`;
      ctx.fillRect(x, y, 2, 2);
    }
    ctx.shadowBlur = 0;

    // bubbles: thin rings with a bright spot, wobbling up
    ctx.strokeStyle = "#cfefff";
    ctx.fillStyle = "#ffffff";
    ctx.lineWidth = 1;
    for (const b of bubbles) {
      b.y -= b.speed * dt;
      if (b.y < -8) blow(b, false);
      const x = Math.round(b.x + Math.sin(t * 1.5 + b.phase) * 2);
      const y = Math.round(b.y);
      ctx.globalAlpha = 0.55;
      ctx.beginPath();
      ctx.arc(x, y, b.r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 0.8;
      ctx.fillRect(Math.round(x - b.r * 0.4), Math.round(y - b.r * 0.5), 1, 1);
    }
    ctx.globalAlpha = 1;
  };

  return {
    attach(next) {
      canvas = next;
      ctx = next.getContext("2d");
    },
    resize,
    frame,
  };
}

const seas = new Map();

export function getSeaLife(key, canvas) {
  if (!seas.has(key)) seas.set(key, createSea());
  const sea = seas.get(key);
  sea.attach(canvas);
  return sea;
}
