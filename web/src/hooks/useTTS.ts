import { useCallback, useEffect, useState } from 'react';

export interface TTS {
  speak: (text: string, options?: { rate?: number }) => void;
  supported: boolean;
  hasArabicVoice: boolean;
}

// Prefer an explicit Arabic voice; iOS reports ar-SA / ar-001, Android often ar-XA.
function pickArabicVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | undefined {
  return voices.find((v) => v.lang?.toLowerCase().startsWith('ar'));
}

export function useTTS(): TTS {
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;
  // hasArabicVoice is observational only — do NOT use it to gate the button.
  // On iOS Safari getVoices() returns [] until the voiceschanged event fires,
  // and that event often only fires after the first user-gesture .speak() call.
  // Gating on it would deadlock the button forever on iPhone.
  const [hasArabicVoice, setHasArabicVoice] = useState<boolean>(() =>
    supported ? !!pickArabicVoice(window.speechSynthesis.getVoices()) : false,
  );

  useEffect(() => {
    if (!supported) return;
    const update = () => setHasArabicVoice(!!pickArabicVoice(window.speechSynthesis.getVoices()));
    update();
    window.speechSynthesis.addEventListener('voiceschanged', update);
    return () => window.speechSynthesis.removeEventListener('voiceschanged', update);
  }, [supported]);

  const speak = useCallback(
    (text: string, options?: { rate?: number }) => {
      if (!supported || !text) return;
      // Stay synchronous: iOS only honors the first .speak() if it happens in
      // the same task as the user gesture — no awaits, no setTimeout, nothing.
      const synth = window.speechSynthesis;
      synth.cancel();
      const u = new SpeechSynthesisUtterance(text);
      // ar-SA resolves on iOS; bare "ar" sometimes does not pick a voice.
      u.lang = 'ar-SA';
      u.rate = options?.rate ?? 1.0;
      // Re-query voices at speak-time: on iOS the list often only populates
      // after the first user-gesture .speak(), so a cached value is stale.
      const voice = pickArabicVoice(synth.getVoices());
      if (voice) {
        u.voice = voice;
        u.lang = voice.lang;
      }
      synth.speak(u);
    },
    [supported],
  );

  return { speak, supported, hasArabicVoice };
}
