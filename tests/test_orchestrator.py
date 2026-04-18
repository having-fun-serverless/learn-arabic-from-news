"""Unit tests for orchestrator step logic (RSS dedupe + index write)."""

from __future__ import annotations

import json
import os
from unittest import mock

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("TABLE_NAME", "test-main")
os.environ.setdefault("ARTICLES_BUCKET", "test-articles")
os.environ.setdefault("PROCESS_FUNCTION_NAME", "test-process-fn")

from orchestrator import handler as orch  # noqa: E402


def _create_table():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="test-main",
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def _fake_feed(links: list[str]):
    class _Entry:
        def __init__(self, link, title="t", summary="hello", published="now"):
            self.link = link
            self.title = title
            self.summary = summary
            self.description = summary
            self.published = published

    class _Feed:
        def __init__(self, entries):
            self.entries = entries

    return _Feed([_Entry(link) for link in links])


@mock_aws
def test_fetch_new_articles_dedupes_via_dynamodb():
    _create_table()
    fake_feed = _fake_feed(["https://x/1", "https://x/2"])
    with mock.patch.object(orch.feedparser, "parse", return_value=fake_feed):
        first = orch.fetch_new_articles()
        second = orch.fetch_new_articles()
    assert len(first) == 2
    assert second == []
    slugs = {a["slug"] for a in first}
    assert len(slugs) == 2  # unique slugs per URL


@mock_aws
def test_fetch_new_articles_skips_entries_without_link():
    _create_table()

    class _E:
        title = "t"
        summary = "s"
        description = "s"
        published = "p"

    e = _E()
    fake = type("F", (), {"entries": [e]})  # no .link attribute
    with mock.patch.object(orch.feedparser, "parse", return_value=fake):
        assert orch.fetch_new_articles() == []


@mock_aws
def test_write_index_aggregates_recent_articles():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-articles")
    payload = {
        "id": "2026-04-18/bbc-abc",
        "source": "bbc",
        "title": {"raw": "عنوان", "diacritized": "عنوان"},
        "tokens": [{"i": 0}, {"i": 1}],
    }
    s3.put_object(
        Bucket="test-articles",
        Key="articles/2026-04-18/bbc-abc.json",
        Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )
    result = orch.write_index("test-articles")
    assert result == {"indexed": 1}

    index = json.loads(s3.get_object(Bucket="test-articles", Key="articles/index.json")["Body"].read())
    assert index["articles"][0]["id"] == "2026-04-18/bbc-abc"
    assert index["articles"][0]["tokenCount"] == 2


def test_slug_is_deterministic_and_short():
    assert orch._slug("https://example.com") == orch._slug("https://example.com")
    assert len(orch._slug("https://example.com")) == 16


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
