"""Per-article NLP bake → S3 JSON.

Pipeline:
  1. Sentence split (pyarabic)
  2. Word tokenize + MLE morphology disambiguation (CAMeL Tools) →
     diacritized form, lemma, POS
  3. Per-lemma Hebrew gloss: DynamoDB cache → AWS Translate on miss
  4. Frequency rank lookup against bundled top-5000 list
  5. Bake JSON → S3 (immutable cache)
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import os
import re
import time
from typing import Any

import boto3

ARTICLES_BUCKET = os.environ.get("ARTICLES_BUCKET", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "")
GLOSS_TTL_SECONDS = 180 * 24 * 60 * 60  # cache lemma glosses for 6 months

_FREQ_PATH = os.path.join(os.path.dirname(__file__), "freq_top5000.json")
# Tashkeel + tatweel + superscript alif: strip these from CAMeL's diacritized
# `lex` so freq + gloss cache lookups land on the bare lemma form.
_DIACRITICS_RE = re.compile(r"[\u064B-\u0652\u0670\u0640]")


@functools.cache
def _freq_table() -> dict[str, int]:
    try:
        with open(_FREQ_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


@functools.cache
def _disambiguator():
    from camel_tools.disambig.mle import MLEDisambiguator

    return MLEDisambiguator.pretrained()


def _split_sentences(text: str) -> list[str]:
    from pyarabic.araby import sentence_tokenize

    return [s.strip() for s in sentence_tokenize(text or "") if s.strip()]


def _tokenize_words(sentence: str) -> list[str]:
    from camel_tools.tokenizers.word import simple_word_tokenize

    return simple_word_tokenize(sentence)


def _strip_diacritics(word: str) -> str:
    return _DIACRITICS_RE.sub("", word)


def _lookup_gloss_cached(lemmas: set[str]) -> dict[str, str | None]:
    """Fetch glosses for `lemmas` from DynamoDB (batch_get) then fill misses
    via AWS Translate ar→he and write them back."""
    if not lemmas or not TABLE_NAME:
        return {lemma: None for lemma in lemmas}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(TABLE_NAME)
    out: dict[str, str | None] = {lemma: None for lemma in lemmas}

    pending = list(lemmas)
    while pending:
        chunk, pending = pending[:100], pending[100:]
        keys = [{"pk": f"lemma#{lemma}", "sk": "gloss"} for lemma in chunk]
        resp = ddb.batch_get_item(RequestItems={TABLE_NAME: {"Keys": keys}})
        for item in resp.get("Responses", {}).get(TABLE_NAME, []):
            lemma = item["pk"].removeprefix("lemma#")
            out[lemma] = item.get("gloss_he")

    misses = [lemma for lemma, g in out.items() if g is None]
    if not misses:
        return out

    translate = boto3.client("translate")
    now = int(time.time())
    with table.batch_writer() as batch:
        for lemma in misses:
            try:
                resp = translate.translate_text(Text=lemma, SourceLanguageCode="ar", TargetLanguageCode="he")
                gloss = resp.get("TranslatedText") or None
            except Exception:
                gloss = None
            out[lemma] = gloss
            if gloss:
                batch.put_item(
                    Item={
                        "pk": f"lemma#{lemma}",
                        "sk": "gloss",
                        "gloss_he": gloss,
                        "lastUsedAt": now,
                        "ttl": now + GLOSS_TTL_SECONDS,
                    }
                )
    return out


def _analyze_sentence(sentence: str) -> list[dict[str, str]]:
    words = _tokenize_words(sentence)
    if not words:
        return []
    disambig = _disambiguator().disambiguate(words)
    out: list[dict[str, str]] = []
    for d in disambig:
        # DisambiguatedWord.analyses is a list of ScoredAnalysis(score, analysis);
        # the first element is the top-scored reading.
        analyses = getattr(d, "analyses", None) or []
        if analyses:
            top = analyses[0].analysis
            diacritized = top.get("diac", d.word)
            lemma = _strip_diacritics(top.get("lex", d.word)) or d.word
            pos = top.get("pos", "unk")
        else:
            diacritized, lemma, pos = d.word, _strip_diacritics(d.word) or d.word, "unk"
        out.append({"raw": d.word, "diacritized": diacritized, "lemma": lemma, "pos": pos})
    return out


def _bake(article: dict[str, Any], today: str) -> dict[str, Any]:
    sentences_raw = _split_sentences(article.get("contentText", ""))
    analyzed = [(sid, _analyze_sentence(s)) for sid, s in enumerate(sentences_raw)]

    all_lemmas = {a["lemma"] for _, words in analyzed for a in words if a["lemma"]}
    glosses = _lookup_gloss_cached(all_lemmas)
    freq = _freq_table()

    tokens: list[dict[str, Any]] = []
    sentences: list[dict[str, Any]] = []
    for sid, words in analyzed:
        start = len(tokens)
        for w in words:
            tokens.append(
                {
                    "i": len(tokens),
                    "raw": w["raw"],
                    "diacritized": w["diacritized"],
                    "lemma": w["lemma"],
                    "pos": w["pos"],
                    "gloss_he": glosses.get(w["lemma"]),
                    "freqRank": freq.get(w["lemma"]),
                    "sentenceId": sid,
                }
            )
        sentences.append({"id": sid, "tokenRange": [start, len(tokens)]})

    title = article.get("title", "") or ""
    return {
        "id": f"{today}/bbc-{article['slug']}",
        "source": "bbc",
        "sourceUrl": article["url"],
        "publishedAt": article.get("publishedAt", ""),
        "title": {"raw": title, "diacritized": title},
        "tokens": tokens,
        "sentences": sentences,
    }


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    today = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    baked = _bake(event, today)
    key = f"articles/{today}/bbc-{event['slug']}.json"
    boto3.client("s3").put_object(
        Bucket=ARTICLES_BUCKET,
        Key=key,
        Body=json.dumps(baked, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
        CacheControl="public, max-age=31536000, immutable",
    )
    return {"id": baked["id"], "key": key, "tokenCount": len(baked["tokens"])}
