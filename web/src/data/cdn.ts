import { useQuery } from '@tanstack/react-query';

const CDN_URL = import.meta.env.VITE_CDN_URL;
if (!CDN_URL) {
  throw new Error('VITE_CDN_URL is not set. Copy .env.example to .env.');
}

export interface IndexEntry {
  id: string;
  date: string;
  slug: string;
  source: string;
  title: string;
  tokenCount: number;
}

export interface ArticleIndex {
  articles: IndexEntry[];
  generatedAt?: string;
}

export interface Token {
  i: number;
  raw: string;
  diacritized: string;
  lemma: string;
  pos: string;
  gloss_he: string;
  freqRank: number | null;
  sentenceId: number;
}

export interface Sentence {
  id: number;
  tokenRange: [number, number];
}

export interface Article {
  id: string;
  source: string;
  sourceUrl: string;
  publishedAt: string;
  title: { raw: string; diacritized: string };
  tokens: Token[];
  sentences: Sentence[];
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${CDN_URL}${path}`);
  if (!res.ok) throw new Error(`Fetch failed: ${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export function useArticleIndex() {
  return useQuery({
    queryKey: ['index'],
    queryFn: () => fetchJson<ArticleIndex>('/articles/index.json'),
    staleTime: 60 * 60 * 1000,
  });
}

export function useArticle(date: string, slug: string) {
  return useQuery({
    queryKey: ['article', date, slug],
    queryFn: () => fetchJson<Article>(`/articles/${date}/${slug}.json`),
    staleTime: Infinity,
  });
}
