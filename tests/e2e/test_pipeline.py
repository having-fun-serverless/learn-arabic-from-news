"""End-to-end test for the daily ingest pipeline.

Runs against the deployed stack. Opt-in via `uv run task e2e`.

Flow:
  1. Resolve stack resources (functions, table, bucket) from CloudFormation.
  2. Clear today's S3 prefix + matching DynamoDB dedupe rows.
  3. Invoke OrchestratorFunction synchronously ($LATEST qualifier — required
     for durable functions).
  4. Assert: ≥1 baked article in S3, index.json count matches, every article's
     URL hash has a dedupe row.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os

import boto3
import pytest

STACK_NAME = os.environ.get("E2E_STACK_NAME", "learn-arabic-from-news")
REGION = os.environ.get("AWS_REGION", "us-east-1")

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def stack():
    cfn = boto3.client("cloudformation", region_name=REGION)

    def physical(logical_id: str) -> str:
        return cfn.describe_stack_resource(StackName=STACK_NAME, LogicalResourceId=logical_id)["StackResourceDetail"][
            "PhysicalResourceId"
        ]

    return {
        "orchestrator": physical("OrchestratorFunction"),
        "table": physical("MainTable"),
        "bucket": physical("ArticlesBucket"),
    }


@pytest.fixture
def today_prefix() -> str:
    return f"articles/{dt.date.today().isoformat()}/"


@pytest.fixture
def clean_today(stack, today_prefix):
    """Delete today's baked articles + their dedupe rows so the run is fresh."""
    s3 = boto3.client("s3", region_name=REGION, endpoint_url=f"https://s3.{REGION}.amazonaws.com")
    ddb = boto3.resource("dynamodb", region_name=REGION).Table(stack["table"])

    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=stack["bucket"], Prefix=today_prefix)
    source_urls: list[str] = []
    delete_keys: list[dict] = []
    for page in pages:
        for obj in page.get("Contents", []):
            delete_keys.append({"Key": obj["Key"]})
            body = s3.get_object(Bucket=stack["bucket"], Key=obj["Key"])["Body"].read()
            url = json.loads(body).get("sourceUrl")
            if url:
                source_urls.append(url)
    if delete_keys:
        s3.delete_objects(Bucket=stack["bucket"], Delete={"Objects": delete_keys})

    with ddb.batch_writer() as batch:
        for url in source_urls:
            pk = f"ingest#{hashlib.sha256(url.encode('utf-8')).hexdigest()}"
            batch.delete_item(Key={"pk": pk, "sk": "seen"})


def test_orchestrator_bakes_articles_end_to_end(stack, today_prefix, clean_today):
    lam = boto3.client("lambda", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION, endpoint_url=f"https://s3.{REGION}.amazonaws.com")
    ddb = boto3.resource("dynamodb", region_name=REGION).Table(stack["table"])

    response = lam.invoke(
        FunctionName=stack["orchestrator"],
        Qualifier="$LATEST",
        Payload=b"{}",
    )
    assert "FunctionError" not in response, response.get("FunctionError")
    payload = json.loads(response["Payload"].read())
    assert payload.get("indexed", 0) >= 1, payload
    assert payload.get("newly_processed", 0) >= 1, payload

    keys = [
        obj["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=stack["bucket"], Prefix=today_prefix)
        for obj in page.get("Contents", [])
    ]
    assert keys, f"no articles under {today_prefix}"

    sample = json.loads(s3.get_object(Bucket=stack["bucket"], Key=keys[0])["Body"].read())
    assert sample["id"].startswith(f"{dt.date.today().isoformat()}/bbc-")
    assert sample["source"] == "bbc"
    assert isinstance(sample["tokens"], list) and sample["tokens"], "no tokens"
    assert {"i", "raw", "diacritized", "lemma", "pos"} <= set(sample["tokens"][0])

    index = json.loads(s3.get_object(Bucket=stack["bucket"], Key="articles/index.json")["Body"].read())
    today_in_index = [a for a in index["articles"] if a["date"] == dt.date.today().isoformat()]
    assert len(today_in_index) == len(keys)

    for key in keys:
        article = json.loads(s3.get_object(Bucket=stack["bucket"], Key=key)["Body"].read())
        url_hash = hashlib.sha256(article["sourceUrl"].encode("utf-8")).hexdigest()
        item = ddb.get_item(Key={"pk": f"ingest#{url_hash}", "sk": "seen"}).get("Item")
        assert item is not None, f"missing dedupe row for {article['sourceUrl']}"
