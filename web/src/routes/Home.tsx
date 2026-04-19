import { Link } from 'wouter';
import { useArticleIndex, type IndexEntry } from '../data/cdn';

const monthsHe = [
  'בינואר',
  'בפברואר',
  'במרץ',
  'באפריל',
  'במאי',
  'ביוני',
  'ביולי',
  'באוגוסט',
  'בספטמבר',
  'באוקטובר',
  'בנובמבר',
  'בדצמבר',
];

function formatDateHe(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return `${d.getUTCDate()} ${monthsHe[d.getUTCMonth()]}`;
}

function articleHref(a: IndexEntry) {
  return `/article/${a.date}/${a.slug}`;
}

export default function Home() {
  const { data, isLoading, error } = useArticleIndex();

  if (isLoading) {
    return (
      <div className="app-shell">
        <p className="loading">טוען…</p>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="app-shell">
        <p className="error">שגיאה בטעינת הכתבות. נסי שוב בעוד רגע.</p>
      </div>
    );
  }

  const articles = data.articles;
  const today = articles[0];
  const rest = articles.slice(1);

  return (
    <div className="app-shell">
      <div className="top-bar">
        <span className="brand-he">אל־ג׳רידה</span>
        <span className="brand-ar" dir="rtl" lang="ar">
          الجريدة
        </span>
      </div>

      {today && (
        <Link href={articleHref(today)} asChild>
          <button className="hero-card" type="button">
            <div className="meta-row">
              <span className="chip chip-ochre">הכתבה של היום</span>
              <span className="chip">{today.tokenCount} מילים</span>
              <span className="dot">·</span>
              <span>{formatDateHe(today.date)}</span>
            </div>
            <div className="ar-title" dir="rtl" lang="ar">
              {today.title}
            </div>
            <span className="cta">
              התחילי לקרוא
              <span aria-hidden>←</span>
            </span>
          </button>
        </Link>
      )}

      {rest.length > 0 && (
        <>
          <div className="section-heading">
            <h2>מהימים האחרונים</h2>
          </div>
          {rest.map((a) => (
            <Link key={`${a.date}/${a.slug}`} href={articleHref(a)} asChild>
              <button className="list-card" type="button">
                <div className="meta-row">
                  <span>{formatDateHe(a.date)}</span>
                  <span className="dot">·</span>
                  <span>{a.tokenCount} מילים</span>
                </div>
                <div className="ar-title" dir="rtl" lang="ar">
                  {a.title}
                </div>
              </button>
            </Link>
          ))}
        </>
      )}
    </div>
  );
}
