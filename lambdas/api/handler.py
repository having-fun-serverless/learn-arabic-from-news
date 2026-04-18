"""API Lambda — HTTP routing via Lambda Powertools event handler."""

import os

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.exceptions import BadRequestError
from aws_lambda_powertools.utilities.typing import LambdaContext

app = APIGatewayHttpResolver()
logger = Logger()
dynamodb = boto3.resource("dynamodb")


@app.get("/api/items")
def list_items() -> dict:
    table = dynamodb.Table(os.environ["TABLE_NAME"])
    result = table.scan(Limit=100)
    return {"items": result.get("Items", [])}


@app.post("/api/items")
def create_item() -> dict:
    body = app.current_event.json_body or {}
    if not body.get("pk") or not body.get("sk"):
        raise BadRequestError("pk and sk are required")
    table = dynamodb.Table(os.environ["TABLE_NAME"])
    table.put_item(Item=body)
    return {"created": True, "item": body}


@logger.inject_lambda_context(log_event=True)
def handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
