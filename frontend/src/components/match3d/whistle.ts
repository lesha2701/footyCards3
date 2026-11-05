/** The referee's whistle, synthesised: two close tones through a fast flutter. */
let ac: AudioContext | null = null;

export function whistle(blasts: number) {
  try {
    ac ??= new AudioContext();
    if (ac.state === "suspended") void ac.resume();
    const start = ac.currentTime + 0.01;
    for (let n = 0; n < blasts; n++) {
      const long = n === blasts - 1;
      const t0 = start + n * 0.42;
      const len = long ? 0.42 : 0.24;
      const gain = ac.createGain();
      gain.gain.setValueAtTime(0, t0);
      gain.gain.linearRampToValueAtTime(0.05, t0 + 0.015);
      gain.gain.setValueAtTime(0.05, t0 + len - 0.05);
      gain.gain.linearRampToValueAtTime(0, t0 + len);
      gain.connect(ac.destination);
      const lfo = ac.createOscillator();
      const depth = ac.createGain();
      lfo.frequency.value = 42;
      depth.gain.value = 90;
      lfo.connect(depth);
      for (const f of [2780, 3020]) {
        const o = ac.createOscillator();
        o.frequency.value = f;
        depth.connect(o.frequency);
        o.connect(gain);
        o.start(t0);
        o.stop(t0 + len + 0.02);
      }
      lfo.start(t0);
      lfo.stop(t0 + len + 0.02);
    }
  } catch {
    // No audio here: the game plays on in silence.
  }
}
