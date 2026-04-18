"""Unit tests for the API Lambda."""

import os

import boto3
from moto import mock_aws

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("TABLE_NAME", "test-table")
os.environ.setdefault("POWERTOOLS_SERVICE_NAME", "test")


@mock_aws
def test_list_items_empty():
    ddb = boto3.resource("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="test-table",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
    )
    from handler import handler

    event = {
        "version": "2.0",
        "routeKey": "GET /api/items",
        "rawPath": "/api/items",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "http": {"method": "GET", "path": "/api/items", "sourceIp": "1.2.3.4"},
            "requestId": "test-id",
        },
        "isBase64Encoded": False,
    }

    class FakeContext:
        function_name = "test"
        memory_limit_in_mb = 128
        invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
        aws_request_id = "test-request"

    response = handler(event, FakeContext())
    assert response["statusCode"] == 200
