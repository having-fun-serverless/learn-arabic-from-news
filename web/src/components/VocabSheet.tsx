import { useEffect } from 'react';
import type { Token } from '../data/cdn';
import { useTTS } from '../hooks/useTTS';
import { uniqueLetters } from '../lib/arabicLetters';
import { posToHebrew } from '../lib/posHebrew';

interface Props {
  token: Token | null;
  open: boolean;
  onClose: () => void;
}

const SpeakerIcon = () => (
  <svg
    viewBox="0 0 24 24"
    width="24"
    height="24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M11 5 L6 9 H3 v6 h3 l5 4 z" />
    <path d="M15 9 a4 4 0 0 1 0 6" />
    <path d="M17.5 6.5 a8 8 0 0 1 0 11" />
  </svg>
);

const SlowSpeakerIcon = () => (
  <svg
    viewBox="0 0 24 24"
    width="24"
    height="24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M11 5 L6 9 H3 v6 h3 l5 4 z" />
    <path d="M15 10.5 a3 3 0 0 1 0 3" />
  </svg>
);

export default function VocabSheet({ token, open, onClose }: Props) {
  const { speak, supported, hasArabicVoice } = useTTS();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const letters = token ? uniqueLetters(token.raw) : [];

  return (
    <>
      <div
        className={'sheet-backdrop' + (open ? ' open' : '')}
        onClick={onClose}
        aria-hidden={!open}
      />
      <div
        className={'sheet' + (open ? ' open' : '')}
        role="dialog"
        aria-modal="true"
        aria-hidden={!open}
      >
        <div className="sheet-grabber" />
        {token && (
          <>
            <div className="sheet-head">
              <div className="sheet-word" dir="rtl" lang="ar">
                {token.diacritized || token.raw}
              </div>
              {supported && (
                <div className="sheet-actions">
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label="השמעה איטית"
                    onClick={() => speak(token.diacritized || token.raw, { rate: 0.5 })}
                    title={hasArabicVoice ? 'השמעה איטית' : 'השמעה איטית (ייתכן שאין קול ערבי במכשיר)'}
                  >
                    <SlowSpeakerIcon />
                  </button>
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label="השמעה"
                    onClick={() => speak(token.diacritized || token.raw)}
                    title={hasArabicVoice ? 'השמעה' : 'השמעה (ייתכן שאין קול ערבי במכשיר)'}
                  >
                    <SpeakerIcon />
                  </button>
                </div>
              )}
            </div>
            <div className="sheet-meta">{posToHebrew(token.pos)}</div>
            <div className="sheet-gloss">{token.gloss_he || '—'}</div>
            <div className="sheet-lemma">
              <span className="sheet-lemma-label">צורת מילון</span>
              <span className="sheet-lemma-value" dir="rtl" lang="ar">
                {token.lemma}
              </span>
            </div>

            {letters.length > 0 && (
              <div className="letter-forms">
                <div className="letter-forms-title">אותיות במילה</div>
                <table className="letter-forms-table" dir="rtl">
                  <thead>
                    <tr>
                      <th>אות</th>
                      <th>שם</th>
                      <th>בודדה</th>
                      <th>בתחילה</th>
                      <th>באמצע</th>
                      <th>בסוף</th>
                    </tr>
                  </thead>
                  <tbody>
                    {letters.map((l) => (
                      <tr key={l.isolated}>
                        <td className="lf-glyph" lang="ar">
                          {l.isolated}
                        </td>
                        <td className="lf-name">{l.name}</td>
                        <td className="lf-glyph" lang="ar">
                          {l.isolated}
                        </td>
                        <td className="lf-glyph" lang="ar">
                          {l.initial ?? '—'}
                        </td>
                        <td className="lf-glyph" lang="ar">
                          {l.medial ?? '—'}
                        </td>
                        <td className="lf-glyph" lang="ar">
                          {l.final ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
