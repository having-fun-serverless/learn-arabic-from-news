import { Link, useParams } from 'wouter';
import { useArticle, type Sentence, type Token } from '../data/cdn';

export default function Article() {
  const params = useParams<{ date: string; slug: string }>();
  const { data, isLoading, error } = useArticle(params.date, params.slug);

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
        {data.title.diacritized}
      </h1>

      {data.sentences.map((s) => (
        <SentenceP key={s.id} sentence={s} tokens={data.tokens} />
      ))}
    </div>
  );
}

function SentenceP({ sentence, tokens }: { sentence: Sentence; tokens: Token[] }) {
  const [start, end] = sentence.tokenRange;
  const slice = tokens.slice(start, end);
  return (
    <p className="ar-body" dir="rtl" lang="ar">
      {slice.map((t, idx) => (
        <span key={t.i}>
          <span className="ar-word">{t.diacritized || t.raw}</span>
          {idx < slice.length - 1 ? ' ' : ''}
        </span>
      ))}
    </p>
  );
}
