"""Per-article NLP bake → S3 JSON.

Pipeline:
  1. Sentence split (pyarabic)
  2. Word tokenize + MLE morphology disambiguation (CAMeL Tools) →
     diacritized form, lemma, POS
  3. One Bedrock call (google.gemma-3-12b-it) per article that returns:
       - Hebrew translation for the title + each sentence (context-aware)
       - Hebrew gloss for every unique lemma (also context-aware)
     DynamoDB caches per-lemma glosses across articles to keep token cost flat.
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
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "google.gemma-3-12b-it")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
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


def _cache_get_glosses(lemmas: set[str]) -> dict[str, str]:
    """Return only the lemmas already cached in DynamoDB (lemma → he gloss)."""
    if not lemmas or not TABLE_NAME:
        return {}
    ddb = boto3.resource("dynamodb")
    out: dict[str, str] = {}
    pending = list(lemmas)
    while pending:
        chunk, pending = pending[:100], pending[100:]
        keys = [{"pk": f"lemma#{lemma}", "sk": "gloss"} for lemma in chunk]
        resp = ddb.batch_get_item(RequestItems={TABLE_NAME: {"Keys": keys}})
        for item in resp.get("Responses", {}).get(TABLE_NAME, []):
            lemma = item["pk"].removeprefix("lemma#")
            gloss = item.get("gloss_he")
            if gloss:
                out[lemma] = gloss
    return out


def _cache_put_glosses(glosses: dict[str, str]) -> None:
    if not glosses or not TABLE_NAME:
        return
    ddb = boto3.resource("dynamodb")
    table = ddb.Table(TABLE_NAME)
    now = int(time.time())
    with table.batch_writer() as batch:
        for lemma, gloss in glosses.items():
            if not gloss:
                continue
            batch.put_item(
                Item={
                    "pk": f"lemma#{lemma}",
                    "sk": "gloss",
                    "gloss_he": gloss,
                    "lastUsedAt": now,
                    "ttl": now + GLOSS_TTL_SECONDS,
                }
            )


_GEMMA_PROMPT = """You are translating a Modern Standard Arabic news clipping
into Hebrew for an adult Hebrew-speaking learner.

Numbered Arabic sentences (the first one is the article title):
{sentences_block}

Unique lemmas (dictionary forms) in the article that need Hebrew glosses:
{lemmas_block}

Return a SINGLE JSON object — no prose, no markdown fences, no commentary —
with this exact shape:
{{
  "sentences": [{{"id": 1, "he": "..."}}, {{"id": 2, "he": "..."}}, ...],
  "lemmas": {{"<arabic_lemma>": "<hebrew_gloss>", ...}}
}}

Rules:
- Hebrew sentence translations must read naturally and concisely.
- Lemma glosses are 1–3 Hebrew words capturing the dictionary meaning in this
  article's context.
- Cover EVERY sentence id and EVERY lemma listed above.
- If a lemma is a particle/affix without a clean Hebrew gloss, return its
  closest Hebrew counterpart (never an empty string).
"""


def _bedrock_translate(sentences: list[str], lemmas: list[str]) -> tuple[dict[int, str], dict[str, str]]:
    """Single Gemma call → (sentence_id → hebrew, lemma → hebrew_gloss).

    Sentence ids are 1-based and align with the order in `sentences`. Returns
    empty dicts on any error so the bake can degrade gracefully.
    """
    if not sentences:
        return {}, {}
    sentences_block = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))
    lemmas_block = ", ".join(lemmas) if lemmas else "(none)"
    prompt = _GEMMA_PROMPT.format(sentences_block=sentences_block, lemmas_block=lemmas_block)

    try:
        client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
        resp = client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 4096, "temperature": 0.0},
        )
        text = resp["output"]["message"]["content"][0]["text"].strip()
    except Exception:
        return {}, {}

    # Extract the first balanced JSON object — Gemma sometimes wraps in fences.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}, {}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}, {}

    sentence_he: dict[int, str] = {}
    for s in data.get("sentences") or []:
        sid = s.get("id")
        he = s.get("he")
        if isinstance(sid, int) and isinstance(he, str) and he.strip():
            sentence_he[sid] = he.strip()
    raw_lemmas = data.get("lemmas") or {}
    lemma_he: dict[str, str] = {k: v.strip() for k, v in raw_lemmas.items() if isinstance(v, str) and v.strip()}
    return sentence_he, lemma_he


def _translate(sentences: list[str], lemmas: set[str]) -> tuple[list[str], dict[str, str]]:
    """Return (per-sentence Hebrew aligned with input order, full lemma→he map).

    Cached lemma glosses are used as-is; only misses are sent to Bedrock and
    written back to the cache. Sentence translations are never cached.
    """
    cached = _cache_get_glosses(lemmas)
    missing = sorted(lemmas - cached.keys())
    sentence_he_by_id, fresh = _bedrock_translate(sentences, missing)
    if fresh:
        _cache_put_glosses(fresh)
    glosses = {**cached, **fresh}
    sentences_he = [sentence_he_by_id.get(i + 1, "") for i in range(len(sentences))]
    return sentences_he, glosses


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
    title = article.get("title", "") or ""
    sentences_raw = _split_sentences(article.get("contentText", ""))
    title_words = _analyze_sentence(title)
    analyzed = [(sid, _analyze_sentence(s)) for sid, s in enumerate(sentences_raw)]

    body_lemmas = {a["lemma"] for _, words in analyzed for a in words if a["lemma"]}
    title_lemmas = {w["lemma"] for w in title_words if w["lemma"]}
    all_lemmas = body_lemmas | title_lemmas

    # Single Gemma call: title is sentence #1 (when present), body sentences follow.
    has_title = bool(title.strip())
    bedrock_input: list[str] = []
    if has_title:
        bedrock_input.append(title)
    bedrock_input.extend(sentences_raw)

    sentences_he, glosses = _translate(bedrock_input, all_lemmas)
    title_he = sentences_he[0] if has_title and sentences_he else ""
    body_he = sentences_he[1:] if has_title else sentences_he

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
        sentences.append(
            {
                "id": sid,
                "tokenRange": [start, len(tokens)],
                "translationHe": body_he[sid] if sid < len(body_he) else "",
            }
        )

    title_tokens = [
        {
            "i": idx,
            "raw": w["raw"],
            "diacritized": w["diacritized"],
            "lemma": w["lemma"],
            "pos": w["pos"],
            "gloss_he": glosses.get(w["lemma"]),
            "freqRank": freq.get(w["lemma"]),
        }
        for idx, w in enumerate(title_words)
    ]
    diacritized_title = " ".join(w["diacritized"] for w in title_words) or title
    return {
        "id": f"{today}/bbc-{article['slug']}",
        "source": "bbc",
        "sourceUrl": article["url"],
        "publishedAt": article.get("publishedAt", ""),
        "title": {
            "raw": title,
            "diacritized": diacritized_title,
            "tokens": title_tokens,
            "translationHe": title_he,
        },
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
