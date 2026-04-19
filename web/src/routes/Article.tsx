import { useState } from 'react';
import { Link, useParams } from 'wouter';
import VocabSheet from '../components/VocabSheet';
import { useArticle, type Sentence, type Token } from '../data/cdn';

export default function Article() {
  const params = useParams<{ date: string; slug: string }>();
  const { data, isLoading, error } = useArticle(params.date, params.slug);
  const [selected, setSelected] = useState<Token | null>(null);

  if (isLoading) {
    return (
      <div className="reader">
        <p className="loading">טוען…</p>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="reader">
        <p className="error">שגיאה בטעינת הכתבה. נסי שוב בעוד רגע.</p>
      </div>
    );
  }

  const titleTokens = data.title.tokens;

  return (
    <div className="reader">
      <Link href="/" asChild>
        <button className="back-link" type="button">
          <span aria-hidden>→</span>
          חזרה לכתבות
        </button>
      </Link>

      <div className="meta-row" style={{ marginTop: 16 }}>
        <span className="chip chip-ochre">{data.source.toUpperCase()}</span>
        <span>{new Date(data.publishedAt).toLocaleDateString('he-IL')}</span>
      </div>

      <h1 className="ar-title" dir="rtl" lang="ar">
        {titleTokens && titleTokens.length > 0
          ? titleTokens.map((t, idx) => (
              <span key={t.i}>
                <Word token={t} isSelected={selected === t} onSelect={() => setSelected(t)} />
                {idx < titleTokens.length - 1 ? ' ' : ''}
              </span>
            ))
          : data.title.diacritized}
      </h1>
      {data.title.translationHe && (
        <p className="he-translation he-translation-title" dir="rtl" lang="he">
          {data.title.translationHe}
        </p>
      )}

      {data.sentences.map((s) => (
        <SentenceP
          key={s.id}
          sentence={s}
          tokens={data.tokens}
          selected={selected}
          onSelect={setSelected}
        />
      ))}

      <VocabSheet token={selected} open={selected !== null} onClose={() => setSelected(null)} />
    </div>
  );
}

interface WordProps {
  token: Token;
  isSelected: boolean;
  onSelect: () => void;
}

function Word({ token, isSelected, onSelect }: WordProps) {
  return (
    <button
      type="button"
      className={'ar-word' + (isSelected ? ' is-selected' : '')}
      onClick={onSelect}
    >
      {token.diacritized || token.raw}
    </button>
  );
}

interface SentenceProps {
  sentence: Sentence;
  tokens: Token[];
  selected: Token | null;
  onSelect: (token: Token) => void;
}

function SentenceP({ sentence, tokens, selected, onSelect }: SentenceProps) {
  const [start, end] = sentence.tokenRange;
  const slice = tokens.slice(start, end);
  return (
    <div className="sentence-block">
      <p className="ar-body" dir="rtl" lang="ar">
        {slice.map((t, idx) => (
          <span key={t.i}>
            <Word token={t} isSelected={selected === t} onSelect={() => onSelect(t)} />
            {idx < slice.length - 1 ? ' ' : ''}
          </span>
        ))}
      </p>
      {sentence.translationHe && (
        <p className="he-translation" dir="rtl" lang="he">
          {sentence.translationHe}
        </p>
      )}
    </div>
  );
}
