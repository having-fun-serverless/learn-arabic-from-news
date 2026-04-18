"""Per-article NLP bake → S3 JSON.

Phase 2: replace the stub tokenizer/diacritizer here with CAMeL Tools morphology
+ AWS Translate gloss lookup (cached in DynamoDB). Schema below stays stable.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Any

import boto3

ARTICLES_BUCKET = os.environ.get("ARTICLES_BUCKET", "")

_TOKEN_RE = re.compile(r"\S+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!؟?])\s+")


def _split_sentences(text: str) -> list[str]:
    chunks = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    return chunks or ([text.strip()] if text.strip() else [])


def _tokenize(sentence: str) -> list[str]:
    return _TOKEN_RE.findall(sentence)


def _bake(article: dict[str, Any], today: str) -> dict[str, Any]:
    sentences_raw = _split_sentences(article.get("contentText", ""))
    tokens: list[dict[str, Any]] = []
    sentences: list[dict[str, Any]] = []

    for sid, sentence in enumerate(sentences_raw):
        start = len(tokens)
        for word in _tokenize(sentence):
            tokens.append(
                {
                    "i": len(tokens),
                    "raw": word,
                    "diacritized": word,
                    "lemma": word,
                    "pos": "unk",
                    "gloss_he": None,
                    "freqRank": None,
                    "sentenceId": sid,
                }
            )
        sentences.append({"id": sid, "tokenRange": [start, len(tokens)]})

    title = article.get("title", "")
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
