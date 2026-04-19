"""Unit tests for the per-article bake function.

The CAMeL Tools morphology + Bedrock path is mocked: those live in the
deployed container image, not the dev machine. The e2e suite covers the real
pipeline against the deployed stack.
"""

from __future__ import annotations

import json
import os
from unittest import mock

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("ARTICLES_BUCKET", "test-articles")
os.environ.setdefault("TABLE_NAME", "test-main")

from process import handler as process_handler  # noqa: E402

SAMPLE_ARTICLE = {
    "url": "https://example.com/news/2026-04-18/headline-one",
    "slug": "abc123",
    "title": "عنوان تجريبي",
    "publishedAt": "2026-04-18T05:30:00Z",
    "contentText": "هذه جملة أولى. هذه جملة ثانية! والثالثة؟ نعم.",
}


def _fake_analysis(words: list[str]) -> list[dict[str, str]]:
    return [{"raw": w, "diacritized": f"{w}\u064f", "lemma": w, "pos": "noun"} for w in words]


@pytest.fixture(autouse=True)
def _stub_nlp(monkeypatch):
    """Replace CAMeL/Bedrock touchpoints with deterministic fakes."""
    monkeypatch.setattr(
        process_handler,
        "_split_sentences",
        lambda text: [s.strip() for s in (text or "").split(".") if s.strip()],
    )
    monkeypatch.setattr(
        process_handler,
        "_analyze_sentence",
        lambda sentence: _fake_analysis(sentence.split()),
    )
    monkeypatch.setattr(
        process_handler,
        "_translate",
        lambda sentences, lemmas: (
            [f"he:{s}" for s in sentences],
            {lemma: f"he:{lemma}" for lemma in lemmas},
        ),
    )
    monkeypatch.setattr(process_handler, "_freq_table", lambda: {})


def test_bake_produces_expected_schema():
    baked = process_handler._bake(SAMPLE_ARTICLE, "2026-04-18")
    assert baked["id"] == "2026-04-18/bbc-abc123"
    assert baked["source"] == "bbc"
    assert baked["sourceUrl"] == SAMPLE_ARTICLE["url"]
    assert baked["title"]["raw"] == "عنوان تجريبي"
    assert baked["title"]["translationHe"] == f"he:{SAMPLE_ARTICLE['title']}"

    sentences = baked["sentences"]
    tokens = baked["tokens"]
    assert len(sentences) >= 2
    assert sentences[0]["tokenRange"][0] == 0
    assert sentences[-1]["tokenRange"][1] == len(tokens)
    for s in sentences:
        assert "translationHe" in s
        assert s["translationHe"].startswith("he:")
    for token in tokens:
        assert {"i", "raw", "diacritized", "lemma", "pos", "gloss_he", "freqRank", "sentenceId"} <= set(token)
        assert token["gloss_he"] == f"he:{token['lemma']}"


def test_bake_handles_empty_content():
    baked = process_handler._bake({**SAMPLE_ARTICLE, "contentText": ""}, "2026-04-18")
    assert baked["tokens"] == []
    assert baked["sentences"] == []


@mock_aws
def test_lambda_handler_writes_to_s3():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-articles")
    with mock.patch.dict(os.environ, {"ARTICLES_BUCKET": "test-articles"}):
        process_handler.ARTICLES_BUCKET = "test-articles"
        result = process_handler.lambda_handler(SAMPLE_ARTICLE, None)

    assert result["tokenCount"] > 0
    obj = s3.get_object(Bucket="test-articles", Key=result["key"])
    body = json.loads(obj["Body"].read())
    assert body["id"] == result["id"]
    assert body["sourceUrl"] == SAMPLE_ARTICLE["url"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
