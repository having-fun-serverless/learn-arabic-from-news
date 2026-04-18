"""Unit tests for the per-article bake function."""

from __future__ import annotations

import json
import os
from unittest import mock

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("ARTICLES_BUCKET", "test-articles")

from process import handler as process_handler  # noqa: E402

SAMPLE_ARTICLE = {
    "url": "https://example.com/news/2026-04-18/headline-one",
    "slug": "abc123",
    "title": "عنوان تجريبي",
    "publishedAt": "2026-04-18T05:30:00Z",
    "contentText": "هذه جملة أولى. هذه جملة ثانية! والثالثة؟ نعم.",
}


def test_bake_produces_expected_schema():
    baked = process_handler._bake(SAMPLE_ARTICLE, "2026-04-18")
    assert baked["id"] == "2026-04-18/bbc-abc123"
    assert baked["source"] == "bbc"
    assert baked["sourceUrl"] == SAMPLE_ARTICLE["url"]
    assert baked["title"]["raw"] == "عنوان تجريبي"

    sentences = baked["sentences"]
    tokens = baked["tokens"]
    assert len(sentences) >= 3
    assert sentences[0]["tokenRange"][0] == 0
    assert sentences[-1]["tokenRange"][1] == len(tokens)
    for token in tokens:
        assert {"i", "raw", "diacritized", "lemma", "pos", "gloss_he", "freqRank", "sentenceId"} <= set(token)


def test_bake_handles_empty_content():
    baked = process_handler._bake({**SAMPLE_ARTICLE, "contentText": ""}, "2026-04-18")
    assert baked["tokens"] == []
    assert baked["sentences"] == []


@mock_aws
def test_lambda_handler_writes_to_s3():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-articles")
    with mock.patch.dict(os.environ, {"ARTICLES_BUCKET": "test-articles"}):
        # reload the module-level constant by patching at use site
        process_handler.ARTICLES_BUCKET = "test-articles"
        result = process_handler.lambda_handler(SAMPLE_ARTICLE, None)

    assert result["tokenCount"] > 0
    obj = s3.get_object(Bucket="test-articles", Key=result["key"])
    body = json.loads(obj["Body"].read())
    assert body["id"] == result["id"]
    assert body["sourceUrl"] == SAMPLE_ARTICLE["url"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
