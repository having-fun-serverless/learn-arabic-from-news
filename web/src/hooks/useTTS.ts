import { useCallback, useEffect, useState } from 'react';

export interface TTS {
  speak: (text: string, options?: { rate?: number }) => void;
  supported: boolean;
  hasArabicVoice: boolean;
}

function pickArabicVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | undefined {
  return voices.find((v) => v.lang?.toLowerCase().startsWith('ar'));
}

export function useTTS(): TTS {
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;
  const [voice, setVoice] = useState<SpeechSynthesisVoice | undefined>(() =>
    supported ? pickArabicVoice(window.speechSynthesis.getVoices()) : undefined,
  );

  useEffect(() => {
    if (!supported) return;
    const update = () => setVoice(pickArabicVoice(window.speechSynthesis.getVoices()));
    update();
    window.speechSynthesis.addEventListener('voiceschanged', update);
    return () => window.speechSynthesis.removeEventListener('voiceschanged', update);
  }, [supported]);

  const speak = useCallback(
    (text: string, options?: { rate?: number }) => {
      if (!supported || !text) return;
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'ar';
      u.rate = options?.rate ?? 1.0;
      if (voice) u.voice = voice;
      window.speechSynthesis.speak(u);
    },
    [supported, voice],
  );

  return { speak, supported, hasArabicVoice: !!voice };
}
