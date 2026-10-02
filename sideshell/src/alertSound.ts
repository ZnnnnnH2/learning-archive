type AudioContextCtor = typeof AudioContext;

declare global {
  interface Window {
    webkitAudioContext?: AudioContextCtor;
  }
}

let audioContext: AudioContext | null = null;
let unlockListenersBound = false;

function getAudioContextCtor(): AudioContextCtor | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.AudioContext ?? window.webkitAudioContext ?? null;
}

function getAudioContext(): AudioContext | null {
  const ctor = getAudioContextCtor();
  if (!ctor) {
    return null;
  }
  if (!audioContext) {
    audioContext = new ctor();
  }
  return audioContext;
}

async function resumeAudioContext(): Promise<AudioContext | null> {
  const context = getAudioContext();
  if (!context) {
    return null;
  }
  if (context.state === "suspended") {
    try {
      await context.resume();
    } catch {
      return null;
    }
  }
  return context;
}

function bindUnlockListeners() {
  if (unlockListenersBound || typeof window === "undefined") {
    return;
  }

  unlockListenersBound = true;
  const unlock = () => {
    void resumeAudioContext();
  };

  for (const eventName of ["pointerdown", "keydown"]) {
    window.addEventListener(eventName, unlock, {
      once: true,
      capture: true,
    });
  }
}

export function primeAlertSound() {
  bindUnlockListeners();
  void resumeAudioContext();
}

export async function playAlertSound(): Promise<void> {
  bindUnlockListeners();
  const context = await resumeAudioContext();
  if (!context) {
    return;
  }

  const now = context.currentTime;
  const oscillator = context.createOscillator();
  const gainNode = context.createGain();

  oscillator.type = "triangle";
  oscillator.frequency.setValueAtTime(880, now);
  oscillator.frequency.exponentialRampToValueAtTime(660, now + 0.18);

  gainNode.gain.setValueAtTime(0.0001, now);
  gainNode.gain.exponentialRampToValueAtTime(0.05, now + 0.01);
  gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.2);

  oscillator.connect(gainNode);
  gainNode.connect(context.destination);

  oscillator.start(now);
  oscillator.stop(now + 0.22);

  oscillator.onended = () => {
    oscillator.disconnect();
    gainNode.disconnect();
  };
}
