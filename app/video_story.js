// §107 story videos in the style the owner sent (a flat 2D cartoon told with captions): characters, places, light and
// camera, all drawn here as SVG — nothing comes from outside, and the model's words only ever go in as textContent.
// Every frame is a pure function of time: the player calls the tick functions with the scene's local time.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const S = (tag, attrs, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const ease = (x) => 1 - Math.pow(1 - clamp(x), 3);
  const W = 1000, H = Math.round(1000 * innerHeight / innerWidth), VERT = H > W;
  const FY = H * (VERT ? .80 : .86);             // the floor line
  const CH = Math.min(H * (VERT ? .40 : .5), 520); // a standing character's height
  let uid = 0;

  // ---------- places (day colours; night = a dark-blue multiply layer + lamps that glow) ----------
  const R = (g, x, y, w, h, fill, rx = 0, extra = {}) => S("rect", Object.assign({ x, y, width: w, height: h, fill, rx }, extra), g);
  const window_ = (g, x, y, w, h, night, bars) => {
    R(g, x - 6, y - 6, w + 12, h + 12, "#e9e4da", 4);
    R(g, x, y, w, h, night ? "#1b2a4a" : "#bfe3f5");
    if (night) S("circle", { cx: x + w * .7, cy: y + h * .3, r: Math.min(w, h) * .12, fill: "#f4f1d0" }, g);
    else S("ellipse", { cx: x + w * .3, cy: y + h * .35, rx: w * .22, ry: h * .08, fill: "#fff", opacity: .8 }, g);
    for (let i = 1; i < (bars ? 6 : 2); i++) R(g, x + w * i / (bars ? 6 : 2) - 2, y, 4, h, "#d8d2c6");
    R(g, x, y + h / 2 - 2, w, 4, "#d8d2c6");
  };
  const door = (g, x, w, h) => { R(g, x, FY - h, w, h, "#8a5a36", 3); R(g, x + w * .2, FY - h * .85, w * .6, h * .3, "#f2f2f2"); S("circle", { cx: x + w * .85, cy: FY - h * .45, r: 5, fill: "#e0b050" }, g); };
  const floorTiles = (g, c1, c2) => {
    R(g, 0, FY, W, H - FY, c1);
    for (let i = 0; i < 12; i++) S("line", { x1: i * W / 11, y1: FY, x2: (i * W / 11 - W / 2) * 1.6 + W / 2, y2: H, stroke: c2, "stroke-width": 3 }, g);
    for (let j = 1; j < 5; j++) S("line", { x1: 0, x2: W, y1: FY + (H - FY) * j * j / 25, y2: FY + (H - FY) * j * j / 25, stroke: c2, "stroke-width": 3 }, g);
  };
  const PLACES = {
    classroom(g, night) {
      R(g, 0, 0, W, FY, "#efe6cf");
      R(g, 0, FY - 40, W, 40, "#d9cdb0");
      const bw = Math.min(W * .5, 520), bx = W / 2 - bw / 2, by = FY - CH * 1.55;
      R(g, bx - 10, by - 10, bw + 20, CH * .7 + 20, "#8a6a45", 4); R(g, bx, by, bw, CH * .7, "#2f6b4b");
      S("path", { d: `M${bx + bw * .1},${by + CH * .2} q${bw * .1},-12 ${bw * .25},0`, stroke: "#cfe3d6", "stroke-width": 3, fill: "none", opacity: .7 }, g);
      R(g, W / 2 - 50, by - CH * .38, 100, 28, "#b5403a", 3);
      S("circle", { cx: W / 2, cy: by - CH * .16, r: 16, fill: "#fff", stroke: "#555", "stroke-width": 3 }, g);
      S("path", { d: `M${W / 2},${by - CH * .16} v-9 M${W / 2},${by - CH * .16} h7`, stroke: "#333", "stroke-width": 2.5 }, g);
      window_(g, W * .04, by - 10, W * .14, CH * .55, night, true);
      R(g, W * .04, FY - CH * .6, W * .1, CH * .6, "#8d96a3", 3); R(g, W * .09 - 1, FY - CH * .55, 2, CH * .5, "#6f7884");
      door(g, W * .8, W * .13, CH * .95);
      R(g, W * .8, by - 4, W * .1, 22, "#3f8f5f", 2);
      floorTiles(g, "#d8d3c7", "#c4beb0");
      for (const x of [.28, .62]) { R(g, W * x, FY - CH * .32, W * .14, 10, "#9a6b44", 2); R(g, W * x + 6, FY - CH * .32, 8, CH * .32, "#7a5235"); R(g, W * x + W * .14 - 14, FY - CH * .32, 8, CH * .32, "#7a5235"); }
      return [{ x: W / 2, y: FY - CH * 1.7, r: 160 }];
    },
    corridor(g, night) {
      R(g, 0, 0, W, H, "#4c5566");
      const vx = W / 2, vy = FY - CH * .9, d = 0.18;
      S("polygon", { points: `0,0 ${W},0 ${vx + W * d},${vy - CH * .4} ${vx - W * d},${vy - CH * .4}`, fill: "#5d6678" }, g);
      S("polygon", { points: `0,${H} ${W},${H} ${vx + W * d},${vy + CH * .5} ${vx - W * d},${vy + CH * .5}`, fill: "#8e8a80" }, g);
      S("polygon", { points: `0,0 ${vx - W * d},${vy - CH * .4} ${vx - W * d},${vy + CH * .5} 0,${H}`, fill: "#6b7486" }, g);
      S("polygon", { points: `${W},0 ${vx + W * d},${vy - CH * .4} ${vx + W * d},${vy + CH * .5} ${W},${H}`, fill: "#626b7d" }, g);
      R(g, vx - W * d, vy - CH * .4, W * 2 * d, CH * .9, night ? "#0d1018" : "#2b2f38");
      for (let i = 0; i < 3; i++) { const k = 1 - i * .28; R(g, vx - 70 * k, vy - CH * .4 - (vy - CH * .4) * k * .8, 140 * k, 10 * k, "#f6f8ff", 4); }
      for (const side of [-1, 1]) for (let i = 0; i < 3; i++) {
        const k = .2 + i * .25, x = side < 0 ? W * k * .5 : W - W * k * .5 - 40;
        R(g, x, vy - CH * .2 + i * 10, 40 * (1 - k * .5), CH * (.55 + k), "#6b4a33", 2);
      }
      return [{ x: vx, y: vy - CH * .6, r: 200 }];
    },
    bathroom(g, night) {
      R(g, 0, 0, W, FY, "#a9b8b5");
      for (let y = 0; y < FY; y += 46) S("line", { x1: 0, x2: W, y1: y, y2: y, stroke: "#97a7a4", "stroke-width": 3 }, g);
      for (let x = 0; x < W; x += 46) S("line", { x1: x, x2: x, y1: 0, y2: FY, stroke: "#97a7a4", "stroke-width": 3 }, g);
      const mw = W * .56, mx = W / 2 - mw / 2, my = FY - CH * 1.35;
      R(g, mx - 12, my - 12, mw + 24, CH * .62 + 24, "#6f7a80", 6); R(g, mx, my, mw, CH * .62, "#cfe0e6");
      S("path", { d: `M${mx + mw * .1},${my + CH * .5} l${mw * .25},-${CH * .4}`, stroke: "#fff", "stroke-width": 8, opacity: .5 }, g);
      R(g, mx, FY - CH * .55, mw, 26, "#e4e7e8", 4);
      for (const x of [.3, .7]) S("ellipse", { cx: mx + mw * x, cy: FY - CH * .5, rx: 46, ry: 12, fill: "#c8ced0" }, g);
      for (let i = 0; i < 2; i++) R(g, i ? W * .86 : 0, FY - CH * 1.25, W * .14, CH * 1.25, "#4d6b67", 2);
      floorTiles(g, "#7f8d8c", "#6e7b7a");
      return [{ x: W / 2, y: my - 40, r: 160 }];
    },
    bedroom(g, night) {
      R(g, 0, 0, W, FY, "#c9d6e3");
      window_(g, W * .62, FY - CH * 1.5, W * .26, CH * .6, night, false);
      R(g, W * .58, FY - CH * 1.58, W * .06, CH * .9, "#e08c7a", 3); R(g, W * .86, FY - CH * 1.58, W * .06, CH * .9, "#e08c7a", 3);
      R(g, W * .1, FY - CH * 1.2, W * .16, CH * .3, "#f2c14e", 3);
      R(g, 0, FY, W, H - FY, "#a98b6a");
      R(g, W * .08, FY - CH * .42, W * .5, CH * .36, "#6d8fc4", 10); R(g, W * .08, FY - CH * .55, W * .1, CH * .5, "#7a5235", 6);
      S("ellipse", { cx: W * .2, cy: FY - CH * .4, rx: W * .06, ry: CH * .06, fill: "#fff" }, g);
      R(g, W * .78, FY - CH * .38, W * .1, CH * .38, "#7a5235", 4);
      S("path", { d: `M${W * .83},${FY - CH * .38} v-${CH * .25}`, stroke: "#444", "stroke-width": 4 }, g);
      S("polygon", { points: `${W * .8},${FY - CH * .63} ${W * .86},${FY - CH * .63} ${W * .88},${FY - CH * .76} ${W * .78},${FY - CH * .76}`, fill: "#f6e7b0" }, g);
      return [{ x: W * .83, y: FY - CH * .7, r: 120 }];
    },
    cafe(g, night) {
      R(g, 0, 0, W, FY, "#e8d8c3");
      R(g, W * .1, FY - CH * 1.55, W * .36, CH * .5, "#3a3a38", 6);
      for (let i = 0; i < 4; i++) R(g, W * .14, FY - CH * 1.45 + i * CH * .1, W * (.2 + (i % 2) * .06), 7, "#f2efe6", 3);
      window_(g, W * .58, FY - CH * 1.5, W * .3, CH * .7, night, false);
      for (const x of [.25, .5, .75]) { S("line", { x1: W * x, x2: W * x, y1: 0, y2: FY - CH * 1.75, stroke: "#333", "stroke-width": 3 }, g); S("path", { d: `M${W * x - 30},${FY - CH * 1.7} q30,-36 60,0 z`, fill: "#2f4f3f" }, g); }
      R(g, 0, FY - CH * .55, W, CH * .55, "#8b5e3c"); R(g, 0, FY - CH * .6, W, 16, "#5f3f28");
      for (const x of [.15, .35]) { R(g, W * x, FY - CH * .74, 26, 30, "#fff", 4); }
      S("circle", { cx: W * .92, cy: FY - CH * .9, r: 40, fill: "#4f8a55" }, g); R(g, W * .9, FY - CH * .9, 20, CH * .35, "#7a5235");
      R(g, 0, FY, W, H - FY, "#6d4c33");
      return [{ x: W * .25, y: FY - CH * 1.65, r: 90 }, { x: W * .5, y: FY - CH * 1.65, r: 90 }, { x: W * .75, y: FY - CH * 1.65, r: 90 }];
    },
    street(g, night) {
      R(g, 0, 0, W, FY, night ? "#1a2546" : "#9fd3ef");
      if (night) S("circle", { cx: W * .8, cy: FY * .2, r: 34, fill: "#f4f1d0" }, g);
      const lights = [];
      let x = 0, i = 0;
      while (x < W) {
        const bw = 120 + (i * 53) % 90, bh = CH * (1 + (i * 37) % 70 / 70);
        R(g, x, FY - bh, bw, bh, ["#7d8597", "#a08f7e", "#8a9a8c", "#9a8aa0"][i % 4]);
        for (let wy = FY - bh + 20; wy < FY - 40; wy += 46) for (let wx = x + 14; wx < x + bw - 30; wx += 40)
          R(g, wx, wy, 22, 26, night ? ((wx + wy) % 3 ? "#2a3350" : "#f3d27a") : "#d9ecf5", 2);
        x += bw + 6; i++;
      }
      R(g, 0, FY - 10, W, 22, "#bdb6aa");
      R(g, 0, FY + 12, W, H - FY, "#3c3f45");
      for (let k = 0; k < 6; k++) R(g, k * W / 5 - 40, FY + (H - FY) * .5, 80, 10, "#e9e3d0");
      for (const lx of [.2, .7]) {
        R(g, W * lx, FY - CH * 1.4, 8, CH * 1.4, "#555");
        R(g, W * lx - 20, FY - CH * 1.42, 48, 12, "#555", 4);
        lights.push({ x: W * lx + 4, y: FY - CH * 1.38, r: 140 });
      }
      return lights;
    },
    office(g, night) {
      R(g, 0, 0, W, FY, "#dfe3e8");
      window_(g, W * .08, FY - CH * 1.55, W * .38, CH * .75, night, false);
      for (let i = 0; i < 8; i++) R(g, W * .08, FY - CH * 1.55 + i * CH * .09, W * .38, 6, "#c6ccd4");
      R(g, W * .6, FY - CH * 1.4, W * .25, CH * .45, "#f6f6f6", 4); R(g, W * .62, FY - CH * 1.33, W * .1, 8, "#4a7bd0");
      R(g, 0, FY, W, H - FY, "#8f97a3");
      for (const dx of [.12, .58]) {
        R(g, W * dx, FY - CH * .42, W * .3, 14, "#d8c6a6", 3);
        R(g, W * dx + 10, FY - CH * .42, 10, CH * .42, "#9c8a6c"); R(g, W * dx + W * .3 - 20, FY - CH * .42, 10, CH * .42, "#9c8a6c");
        R(g, W * dx + W * .08, FY - CH * .7, W * .13, CH * .26, "#2b2f38", 4); R(g, W * dx + W * .085, FY - CH * .68, W * .12, CH * .21, night ? "#7fb3ff" : "#5a8fd8", 2);
      }
      return [{ x: W * .2, y: FY - CH * .6, r: 90 }, { x: W * .66, y: FY - CH * .6, r: 90 }];
    },
    livingroom(g, night) {
      R(g, 0, 0, W, FY, "#e9dcc6");
      window_(g, W * .06, FY - CH * 1.5, W * .24, CH * .7, night, false);
      R(g, W * .6, FY - CH * 1.2, W * .3, CH * .45, "#1f2228", 6); R(g, W * .615, FY - CH * 1.17, W * .27, CH * .39, night ? "#3d6fb6" : "#2c3440", 3);
      R(g, W * .62, FY - CH * .72, W * .26, CH * .2, "#7a5235", 4);
      R(g, 0, FY, W, H - FY, "#b08a62");
      S("ellipse", { cx: W * .5, cy: FY + (H - FY) * .4, rx: W * .35, ry: (H - FY) * .25, fill: "#c75b4a", opacity: .8 }, g);
      R(g, W * .14, FY - CH * .5, W * .4, CH * .32, "#5a7f9a", 12); R(g, W * .14, FY - CH * .72, W * .4, CH * .26, "#4d7089", 12);
      R(g, W * .44, FY - CH * .9, 10, CH * .9, "#555"); S("polygon", { points: `${W * .42},${FY - CH * .9} ${W * .47},${FY - CH * .9} ${W * .49},${FY - CH * 1.02} ${W * .4},${FY - CH * 1.02}`, fill: "#f6e7b0" }, g);
      return [{ x: W * .445, y: FY - CH * .95, r: 130 }, { x: W * .75, y: FY - CH * .95, r: 150 }];
    },
  };

  // ---------- characters ----------
  // look: {gender, hair, hairColor, skin, top, color, glasses, age} — from the script's cast line, checked in video.py
  function character(look, idx) {
    const g = S("g"), stool = R(g, -13, -19, 26, 19, "#7a5235", 3), body = S("g", {}, g), headG = S("g", {}, body);
    const skin = look.skin, top = look.color, dark = "#2b2b33", hairC = look.hairColor;
    const parts = {};
    // legs (stand / walk / sit swap them)
    const legL = S("g", {}, body), legR = S("g", {}, body);
    for (const [leg, x] of [[legL, -6], [legR, 6]]) {
      R(leg, x - 4.5, -36, 9, 32, look.top === "dress" ? skin : "#2d3a55", 3);
      S("ellipse", { cx: x + 1, cy: -3, rx: 6.5, ry: 3.2, fill: "#e8e8ea" }, leg);
    }
    parts.legs = [legL, legR];
    // torso
    const torso = S("g", {}, body);
    if (look.top === "dress") S("path", { d: "M-12,-66 L12,-66 L17,-30 L-17,-30 Z", fill: top }, torso);
    else R(torso, -13, -67, 26, 34, top, 6);
    if (look.top === "student" || look.top === "shirt") {
      S("path", { d: "M-6,-67 L0,-58 L6,-67", stroke: "#b9bcc4", "stroke-width": 1.6, fill: "none" }, torso);
      R(torso, -5, -48, 10, 7, "#c9ccd3", 2);
    } else if (look.top === "hoodie") {
      S("path", { d: "M-9,-67 Q0,-60 9,-67", stroke: "#00000033", "stroke-width": 3, fill: "none" }, torso);
      R(torso, -7, -46, 14, 8, "#00000022", 3);
      S("line", { x1: -2, y1: -64, x2: -2, y2: -56, stroke: "#fff", "stroke-width": 1 }, torso); S("line", { x1: 2, y1: -64, x2: 2, y2: -56, stroke: "#fff", "stroke-width": 1 }, torso);
    } else if (look.top === "suit") {
      S("path", { d: "M-5,-67 L0,-55 L5,-67 Z", fill: "#fff" }, torso); S("path", { d: "M-1.5,-63 L1.5,-63 L1,-52 L-1,-52 Z", fill: "#b5403a" }, torso);
    }
    // arms: back arm static, front arm posable
    const armB = S("g", {}, body), armF = S("g", {}, body);
    for (const a of [armB, armF]) { R(a, -3, 0, 6, 26, top, 3); S("circle", { cx: 0, cy: 27, r: 3.4, fill: skin }, a); }
    armB.setAttribute("transform", "translate(-12,-64) rotate(8)"); parts.armF = armF;
    const phone = R(armF, -3, 26, 6, 10, "#1d1f24", 1.5); phone.style.display = "none"; parts.phone = phone;
    // head
    body.appendChild(headG);
    // long hair falls down the sides only (under the chin it read as a beard)
    if (look.hair === "long") S("path", { d: "M-15,-84 Q-18,-62 -14,-56 L-9,-58 Q-12,-68 -12,-78 L12,-78 Q12,-68 9,-58 L14,-56 Q18,-62 15,-84 Z", fill: hairC }, headG);
    S("circle", { cx: -14, cy: -79, r: 3.2, fill: skin }, headG); S("circle", { cx: 14, cy: -79, r: 3.2, fill: skin }, headG);
    S("ellipse", { cx: 0, cy: -80, rx: 14, ry: 13, fill: skin }, headG);
    const hairPath = {
      short: "M-14,-81 Q-15,-96 0,-95 Q15,-96 14,-81 L11,-86 L8,-83 L5,-87 L1,-84 L-3,-88 L-7,-84 L-11,-87 Z",
      long: "M-14.5,-79 Q-15,-97 0,-95 Q15,-97 14.5,-79 Q8,-90 0,-89 Q-8,-90 -14.5,-79 Z",
      ponytail: "M-14.5,-80 Q-15,-97 0,-95 Q15,-97 14.5,-80 Q6,-89 -14.5,-80 Z",
      curly: "M-15,-80 q-3,-8 2,-11 q0,-7 7,-6 q4,-5 10,0 q7,-1 7,6 q5,3 2,11 q-4,-6 -14,-6 q-10,0 -14,6 Z",
      bald: "",
    }[look.hair] || "";
    if (hairPath) S("path", { d: hairPath, fill: hairC }, headG);
    if (look.hair === "ponytail") S("ellipse", { cx: 15, cy: -86, rx: 4, ry: 9, fill: hairC, transform: "rotate(30 15 -86)" }, headG);
    // face
    const face = S("g", {}, headG), eyes = S("g", {}, face);
    const eyeW = [], pupils = [], brows = [];
    for (const x of [-5, 5]) {
      eyeW.push(S("ellipse", { cx: x, cy: -80, rx: 3.6, ry: 3.8, fill: "#fff" }, eyes));
      pupils.push(S("circle", { cx: x + .6, cy: -79.6, r: 1.7, fill: "#1a1a1a" }, eyes));
      brows.push(S("line", { x1: x - 3, y1: -86, x2: x + 3, y2: -86, stroke: "#2a1d14", "stroke-width": 1.8, "stroke-linecap": "round" }, face));
    }
    const closed = S("path", { d: "M-8,-80 q3,2 6,0 M2,-80 q3,2 6,0", stroke: "#2a1d14", "stroke-width": 1.4, fill: "none" }, face);
    const mouth = S("path", { fill: "#7a2e2a", stroke: "#4a1d1a", "stroke-width": 1.2, "stroke-linecap": "round" }, face);
    const sweat = S("path", { d: "M10,-90 q-2.4,3.4 0,4.6 q2.4,-1.2 0,-4.6 z", fill: "#7cc7ff" }, face);
    const zzz = S("text", { x: 14, y: -96, "font-size": 7, fill: "#ffffffaa", "font-weight": 700 }, face);
    zzz.textContent = "z";
    if (look.glasses) for (const x of [-5, 5]) S("circle", { cx: x, cy: -80, r: 4.6, fill: "none", stroke: "#222", "stroke-width": 1.2 }, face);
    if (look.age === "old") { S("path", { d: "M-9,-71 q9,4 18,0", stroke: "#00000022", "stroke-width": 1, fill: "none" }, face); }
    const blinkAt = 1.7 + idx * 1.3;

    // lying in bed (seen from above, like the reference): pillow, head, blanket
    const bed = S("g"); const bedHead = S("g", {}, bed);
    S("ellipse", { cx: 0, cy: -80, rx: 24, ry: 16, fill: "#d6dae3" }, bed);
    bed.insertBefore(bed.lastChild, bedHead);
    R(bed, -22, -66, 44, 66, ["#3e5f86", "#4f7a55", "#7a4f6d", "#8a6a3c"][idx % 4], 4);

    function setFace(kind, L, talking) {
      const blink = ((L + blinkAt) % 3.4) < .12 && kind !== "sleep";
      eyes.style.display = blink || kind === "sleep" ? "none" : "";
      closed.style.display = blink || kind === "sleep" ? "" : "none";
      sweat.style.display = kind === "scared" ? "" : "none";
      zzz.style.display = kind === "sleep" ? "" : "none";
      if (kind === "sleep") zzz.setAttribute("y", -96 - (L * 6) % 8);
      const small = kind === "shock" || kind === "scared";
      pupils.forEach((p) => p.setAttribute("r", small ? 1.1 : 1.7));
      eyeW.forEach((e) => e.setAttribute("ry", kind === "smirk" ? 2.4 : kind === "shock" ? 4.4 : 3.8));
      const by = { shock: -89, scared: -87, sad: -86 }[kind] || -86;
      brows.forEach((b, i) => {
        const s = i ? 1 : -1;  // left / right
        const inner = { angry: 2.6, scared: -2.2, sad: -2.2, smirk: i ? -2 : 1 }[kind] || 0;
        b.setAttribute("x1", s * 2); b.setAttribute("x2", s * 8);
        b.setAttribute("y1", by + inner); b.setAttribute("y2", by - (kind === "angry" ? 1 : 0));
      });
      let open = { shock: 3.2, scared: 1.4 }[kind] || 0;
      if (talking) open = Math.max(open, 1.2 + 1.6 * Math.abs(Math.sin(L * 13) * Math.sin(L * 5.3)));
      if (open > .3) mouth.setAttribute("d", `M-3,${-71.5 - open / 2} Q0,${-72 - open} 3,${-71.5 - open / 2} Q3,${-71 + open} 0,${-71 + open} Q-3,${-71 + open} -3,${-71.5 - open / 2} Z`);
      else if (kind === "smile") mouth.setAttribute("d", "M-4,-72 Q0,-68 4,-72");
      else if (kind === "smirk") mouth.setAttribute("d", "M-3,-71 Q1,-70 4,-73");
      else if (kind === "sad" || kind === "angry") mouth.setAttribute("d", "M-3.5,-70 Q0,-73 3.5,-70");
      else mouth.setAttribute("d", "M-2.5,-71.5 L2.5,-71.5");
      mouth.setAttribute("fill", open > .3 ? "#7a2e2a" : "none");
    }

    return {
      g, bed, look,
      place(pose, x, facing, s) {  // put in the world; returns where the head is (for the camera)
        const lying = pose === "lie";
        if (lying) { bedHead.appendChild(headG); g.appendChild(bed); body.style.display = "none"; }
        else { body.insertBefore(headG, null); if (bed.parentNode) g.removeChild(bed); body.style.display = ""; }
        const scale = s * CH / 100, y = lying ? FY - CH * .05 : FY;
        g.setAttribute("transform", `translate(${x},${y}) scale(${facing * scale},${scale})`);
        return { x, y: y - (lying ? 72 : 80) * scale, scale };
      },
      pose(kind, L, face, talking, flash) {
        const swing = kind === "walk" ? Math.sin(L * 7) * 16 : 0, sit = kind === "sit";
        stool.style.display = sit ? "" : "none";
        parts.legs.forEach((l, i) => l.setAttribute("transform", `rotate(${sit ? -80 : i ? -swing : swing} ${i ? 6 : -6} -36)`));
        body.setAttribute("transform", `translate(0,${(sit ? 20 : 0) + Math.sin(L * 2.2 + idx) * .5 + (kind === "walk" ? Math.abs(Math.sin(L * 7)) * -1.2 : 0)})`);
        const raised = kind === "flashlight" || kind === "point" || kind === "phone";
        parts.armF.setAttribute("transform", raised ? "translate(12,-64) rotate(-95)" : `translate(12,-64) rotate(${-8 + swing * .4})`);
        parts.phone.style.display = kind === "flashlight" || kind === "phone" ? "" : "none";
        setFace(face, L, talking);
        if (flash && kind === "flashlight") return { hand: true };
        return null;
      },
    };
  }

  function ghost(g) {
    const gh = S("g", {}, g);
    S("path", { d: "M-14,-82 Q-16,-100 0,-100 Q16,-100 14,-82 L17,-40 L14,0 L-14,0 L-17,-40 Z", fill: "#050507" }, gh);
    S("path", { d: "M-15,-84 Q-19,-55 -13,-30 L13,-30 Q19,-55 15,-84 Z", fill: "#0b0b0e" }, gh);
    return gh;
  }

  // ---------- captions: *yellow* · **red box** · "ต้น: …" speaker in yellow (owner's style choice: story / simple / none) ----------
  function caption(box, speaker, text, style) {
    if (style === "none" || !text) return;
    if (speaker) { const sp = document.createElement("span"); sp.className = "c-speaker"; sp.textContent = speaker + ": "; box.appendChild(sp); }
    for (const part of String(text).split(/(\*\*[^*]+\*\*|\*[^*]+\*)/)) {
      if (!part) continue;
      const span = document.createElement("span");
      if (style === "story" && part.startsWith("**")) { span.className = "c-red"; span.textContent = part.slice(2, -2); }
      else if (style === "story" && part.startsWith("*")) { span.className = "c-yellow"; span.textContent = part.slice(1, -1); }
      else span.textContent = part.replace(/\*/g, "");
      box.appendChild(span);
    }
  }

  // ---------- one shot ----------
  function shot(s, n, parts) {
    n.classList.add("shotscene");
    const root = S("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMid slice", class: "world" }, n);
    const defs = S("defs", {}, root);
    const vg = "v" + (++uid), fl = "f" + uid, gl = "g" + uid;
    const rg = S("radialGradient", { id: vg, cx: "50%", cy: "48%", r: "70%" }, defs);
    S("stop", { offset: "55%", "stop-color": "#000", "stop-opacity": 0 }, rg); S("stop", { offset: "100%", "stop-color": "#000", "stop-opacity": .75 }, rg);
    const lg = S("linearGradient", { id: fl, x1: "0", y1: "0", x2: "1", y2: "0" }, defs);
    S("stop", { offset: "0", "stop-color": "#fffbe6", "stop-opacity": .75 }, lg); S("stop", { offset: "1", "stop-color": "#fffbe6", "stop-opacity": 0 }, lg);
    const glow = S("radialGradient", { id: gl }, defs);
    S("stop", { offset: "0", "stop-color": "#fff6d8", "stop-opacity": .55 }, glow); S("stop", { offset: "1", "stop-color": "#fff6d8", "stop-opacity": 0 }, glow);

    const world = S("g", {}, root), bg = S("g", {}, world);
    const night = s.time === "night";
    const lamps = (PLACES[s.place] || PLACES.classroom)(bg, night) || [];
    const actors = S("g", {}, world);
    let gh = null;
    if (s.ghost) { gh = ghost(actors); }
    const chars = (s.cast || []).map((c, i) => {
      const ch = character(c.look, c.index != null ? c.index : i);
      actors.appendChild(ch.g);
      return { c, ch };
    });
    const nightL = S("rect", { x: 0, y: 0, width: W, height: H, fill: "#0a1638", opacity: night ? .8 : 0, style: "mix-blend-mode:multiply" }, world);
    const glows = S("g", { style: "mix-blend-mode:screen" }, world);
    if (night) lamps.forEach((l) => S("circle", { cx: l.x, cy: l.y, r: l.r, fill: `url(#${gl})` }, glows));
    const beam = S("polygon", { fill: `url(#${fl})`, style: "mix-blend-mode:screen", opacity: 0 }, world);
    S("rect", { x: 0, y: 0, width: W, height: H, fill: `url(#${vg})`, opacity: night ? 1 : .35 }, root);

    // HTML on top: badge (clock) and caption
    if (s.badge) { const b = document.createElement("div"); b.className = "badge"; b.textContent = "🕒 " + s.badge; n.appendChild(b); }
    if (SB.captions !== "none") { const sh = document.createElement("div"); sh.className = "capshade"; n.appendChild(sh); }  // words stay readable on a light place
    const cap = document.createElement("div");
    cap.className = "caption " + (SB.captions === "simple" ? "c-simple" : "");
    caption(cap, s.speaker, s.text, SB.captions || "story");
    n.appendChild(cap);

    // where everyone stands: in order across the floor, facing the middle (the speaker turns to whoever is there)
    const k = chars.length;
    const tick = (L) => {
      let focus = null, beamFrom = null;
      chars.forEach(({ c, ch }, i) => {
        const x = W * (c.x != null ? c.x : k === 1 ? .5 : .2 + .6 * i / Math.max(1, k - 1));
        const facing = c.facing || (x < W / 2 ? 1 : -1);
        const walk = c.pose === "walk" ? (L - s.seconds / 2) * W * .03 * facing : 0;
        const at = ch.place(c.pose, x + walk, facing, c.pose === "lie" ? 1.05 : 1);
        const talking = s.speaker === c.name && L > s.talk0 && L < s.talk1;
        const r = ch.pose(c.pose, L, c.face, talking, night);
        if (s.speaker === c.name || (!focus && i === 0)) focus = at;
        if (r && r.hand) beamFrom = { x: at.x + facing * 30 * at.scale, y: at.y + 18 * at.scale, facing };
      });
      if (gh) {
        gh.setAttribute("transform", `translate(${W * (s.ghostX || .82)},${FY - CH * .15}) scale(${CH / 115})`);
        gh.style.opacity = .55 + .35 * Math.sin(L * 9) * Math.sin(L * 2.3);
      }
      if (beamFrom) {
        const f = beamFrom.facing, len = W * 1.1, spread = H * .22, x2 = beamFrom.x + f * len;
        beam.setAttribute("points", `${beamFrom.x},${beamFrom.y} ${x2},${beamFrom.y - spread} ${x2},${beamFrom.y + spread}`);
        beam.style.opacity = .85 + .1 * Math.sin(L * 23);
      } else beam.style.opacity = 0;
      // camera: wide · close (on the speaker) · push · pan · a punch on a shock
      let z = 1, fx = W / 2, fy = H / 2;
      const p = L / s.seconds;
      if (s.camera === "close" && focus) { z = VERT ? 1.9 : 1.6; fx = focus.x; fy = focus.y + CH * (VERT ? .12 : .2); }
      else if (s.camera === "pan") { z = 1.18; fx = W * (.4 + .2 * p); }
      z *= 1 + .05 * p;  // a slow push in every shot
      if (chars.some(({ c }) => c.face === "shock")) z *= 1 + .07 * (1 - ease(L / .3));
      const tx = clamp(W / 2 - z * fx, W - z * W, 0), ty = clamp(H * .46 - z * fy, H - z * H, 0);
      world.setAttribute("transform", `translate(${tx},${ty}) scale(${z})`);
      cap.style.opacity = ease(L / .2);
    };
    n._tick = tick;
    parts.push([n, 0, "tick"]);
  }

  function card(s, n, parts) {
    n.classList.add("endcard");
    const t = document.createElement("div"); t.className = "end-title"; t.textContent = s.text; n.appendChild(t);
    if (s.sub) { const u = document.createElement("div"); u.className = "end-sub"; u.textContent = s.sub; n.appendChild(u); }
    const bar = document.createElement("div"); bar.className = "end-bar"; n.appendChild(bar);
    n._tick = (L) => { t.style.opacity = ease(L / .6); t.style.transform = `scale(${1.08 - .08 * ease(L / .8)})`; bar.style.width = ease((L - .3) / .8) * 40 + "%"; };
    parts.push([n, 0, "tick"]);
  }

  window.STORY = { shot, card };
})();
