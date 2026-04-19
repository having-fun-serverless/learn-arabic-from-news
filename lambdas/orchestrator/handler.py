"""Daily ingestion orchestrator (BBC Arabic RSS → process → index)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

import boto3
import feedparser
from aws_durable_execution_sdk_python import (
    DurableContext,
    StepContext,
    durable_execution,
    durable_step,
)

BBC_ARABIC_RSS = "https://feeds.bbci.co.uk/arabic/rss.xml"
DEDUPE_TTL_SECONDS = 30 * 24 * 60 * 60
INDEX_KEY = "articles/index.json"
INDEX_LIMIT = 30


def _ddb_table():
    return boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def _s3():
    return boto3.client("s3")


def _slug(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def fetch_new_articles(feed_url: str = BBC_ARABIC_RSS) -> list[dict[str, Any]]:
    """Pure-ish: parse RSS, dedupe via DynamoDB, return new articles & mark them seen."""
    parsed = feedparser.parse(feed_url)
    table = _ddb_table()
    fresh: list[dict[str, Any]] = []
    now = int(time.time())

    for entry in parsed.entries:
        url = getattr(entry, "link", None)
        if not url:
            continue
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        pk = f"ingest#{url_hash}"
        if table.get_item(Key={"pk": pk, "sk": "seen"}).get("Item"):
            continue

        table.put_item(
            Item={
                "pk": pk,
                "sk": "seen",
                "firstSeenAt": now,
                "ttl": now + DEDUPE_TTL_SECONDS,
            }
        )
        fresh.append(
            {
                "url": url,
                "slug": _slug(url),
                "title": getattr(entry, "title", ""),
                "publishedAt": getattr(entry, "published", ""),
                "contentText": getattr(entry, "summary", "") or getattr(entry, "description", ""),
            }
        )

    return fresh


def write_index(bucket: str) -> dict[str, Any]:
    """List baked articles in S3 and write articles/index.json (most recent 30)."""
    s3 = _s3()
    keys: list[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="articles/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json") and key != INDEX_KEY:
                keys.append(key)
    keys.sort(reverse=True)

    entries: list[dict[str, Any]] = []
    for key in keys[:INDEX_LIMIT]:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        article = json.loads(body)
        article_id = article["id"]
        date, slug = article_id.split("/", 1)
        title_obj = article.get("title", {})
        entries.append(
            {
                "id": article_id,
                "date": date,
                "slug": slug,
                "source": article.get("source", "bbc"),
                "title": title_obj.get("diacritized") or title_obj.get("raw", ""),
                "tokenCount": len(article.get("tokens", [])),
            }
        )

    s3.put_object(
        Bucket=bucket,
        Key=INDEX_KEY,
        Body=json.dumps({"articles": entries}, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
        CacheControl="public, max-age=3600",
    )
    return {"indexed": len(entries)}


@durable_step
def ingest_step(step_ctx: StepContext) -> list[dict[str, Any]]:
    fresh = fetch_new_articles()
    step_ctx.logger.info("ingest_complete", extra={"new_articles": len(fresh)})
    return fresh


@durable_step
def index_step(step_ctx: StepContext, processed: list[dict[str, Any]]) -> dict[str, Any]:
    result = write_index(os.environ["ARTICLES_BUCKET"])
    step_ctx.logger.info("index_written", extra={**result, "newly_processed": len(processed)})
    return {**result, "newly_processed": len(processed)}


def _process_one(context: DurableContext, article: dict[str, Any], _idx: int, _all: list[dict[str, Any]]):
    return context.invoke(
        function_name=os.environ["PROCESS_FUNCTION_NAME"],
        payload=article,
        name=f"process_{article['slug']}",
    )


@durable_execution
def handler(event: dict[str, Any], context: DurableContext) -> dict[str, Any]:
    context.logger.info("orchestrator_start", extra={"event": event})
    articles = context.step(ingest_step(), name="ingest")
    if not articles:
        context.logger.info("no_new_articles")
        return context.step(index_step([]), name="index")
    processed = context.map(articles, _process_one, name="process_each")
    processed.throw_if_error()
    return context.step(index_step(processed.get_results()), name="index")
