// Audio: background music (HTMLAudioElement, autoplay-gesture-gated) + short
// WebAudio SFX blips (no audio files for SFX — synthesized square-wave beeps).
//
// Nothing here runs at module top level; `createAudio()` builds everything on
// call, and `new Audio(...)`/AudioContext are only touched from inside methods
// so importing this module has no side effects (mirrors game.js's pattern).
export function createAudio() {
  let music = null;
  let musicSrc = null;   // MediaElementAudioSourceNode wrapping the <audio>
  let musicGain = null;  // GainNode that actually controls music loudness
  let musicVolume = 0.28; // 0..1; overridden by /admin/settings via setMusicVolume
  let muted = false;
  let ctx = null; // lazily-created WebAudio context, for SFX oscillators + music gain

  function getMusic() {
    if (!music) {
      music = new Audio("/static/assets/music.mp3");
      music.loop = true;
    }
    return music;
  }

  function getCtx() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC();
    }
    return ctx;
  }

  // Route the background <audio> through a GainNode. This is the whole point of
  // the module's audio graph: on iOS `HTMLAudioElement.volume` is READ-ONLY and
  // silently ignored (volume is hardware-only there), so setting music.volume
  // never made the track quieter on iPhones. A Web Audio GainNode DOES control
  // loudness on iOS. Created once (a MediaElementSource can only wrap an element
  // a single time); safe to call repeatedly. Falls back to element.volume if the
  // Web Audio graph can't be built.
  function routeMusic() {
    if (musicSrc || !music) return;
    try {
      const c = getCtx();
      musicSrc = c.createMediaElementSource(music);
      musicGain = c.createGain();
      musicGain.gain.value = muted ? 0 : musicVolume;
      musicSrc.connect(musicGain);
      musicGain.connect(c.destination);
    } catch (_) {
      // No Web Audio for media elements — best effort (ignored on iOS).
      try { music.volume = musicVolume; } catch (_) { /* ignore */ }
    }
  }

  function applyMusicLevel() {
    if (musicGain) musicGain.gain.value = muted ? 0 : musicVolume;
    else if (music) { try { music.volume = muted ? 0 : musicVolume; } catch (_) { /* ignore */ } }
  }

  // Short square-wave blip, scheduled `startOffset` seconds from now (0 for
  // an immediate blip). Guarded so a missing/blocked AudioContext never throws.
  function blipAt(freq, startOffset, dur) {
    try {
      const c = getCtx();
      const osc = c.createOscillator();
      const gain = c.createGain();
      osc.type = "square";
      osc.frequency.value = freq;
      gain.gain.value = 0.15;
      osc.connect(gain);
      gain.connect(c.destination);
      const start = c.currentTime + startOffset;
      osc.start(start);
      gain.gain.setValueAtTime(0.15, start);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + dur);
      osc.stop(start + dur);
    } catch (_) { /* WebAudio unavailable — ignore */ }
  }

  function blip(freq, dur) {
    blipAt(freq, 0, dur);
  }

  return {
    // Call from a user-gesture handler (e.g. the "Играть" click). Autoplay
    // policies may still reject play() (e.g. no gesture, or the mp3 is
    // missing) — swallow so the game never crashes over audio.
    startMusic() {
      if (muted) return;
      const m = getMusic();
      routeMusic();
      // The context starts "suspended" until a user gesture — resume it so the
      // gain graph (and thus the music) is actually audible on the play tap.
      if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
      try {
        const p = m.play();
        if (p && typeof p.then === "function") p.catch(() => {});
      } catch (_) { /* ignore */ }
    },
    // Music loudness only (0..1), from /admin/settings. SFX are unaffected — they
    // keep their own fixed gain, per the requirement that only music is tunable.
    setMusicVolume(v) {
      const n = Number(v);
      musicVolume = Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : musicVolume;
      applyMusicLevel();
    },
    // Toggles mute, applied via the gain node (works on iOS); returns the new
    // muted state so the caller (boot.js) can swap the mute-button icon.
    toggleMute() {
      muted = !muted;
      applyMusicLevel();
      if (music) music.muted = muted; // belt-and-suspenders (element level too)
      if (!muted) this.startMusic();
      return muted;
    },
    sfxJump() {
      blip(660, 0.08);
    },
    sfxGameOver() {
      blip(220, 0.25);
    },
    // Short victory sting for revealing a new lyric line: 3 ascending notes.
    sfxReveal() {
      blipAt(523, 0, 0.1);
      blipAt(659, 0.11, 0.1);
      blipAt(784, 0.22, 0.12);
    },
  };
}
