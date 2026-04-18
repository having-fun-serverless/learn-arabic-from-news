"""Lambda Authorizer — validates Bearer token against Secrets Manager."""

import hashlib
import hmac
import os

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities import parameters
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()


@logger.inject_lambda_context(log_event=True)
def handler(event: dict, context: LambdaContext) -> dict:
    identity_source = event.get("identitySource", "")
    if isinstance(identity_source, list):
        identity_source = identity_source[0] if identity_source else ""

    received_token = _extract_bearer_token(identity_source)
    if not received_token:
        return {"isAuthorized": False}

    secret = parameters.get_secret(os.environ["SECRET_NAME"], transform="json")
    expected = hashlib.sha256(
        f"{secret['username']}:{secret['password']}".encode()
    ).hexdigest()

    if hmac.compare_digest(received_token, expected):
        return {"isAuthorized": True, "context": {"username": secret["username"]}}
    return {"isAuthorized": False}


def _extract_bearer_token(header_value: str) -> str | None:
    parts = header_value.split(" ", 1) if header_value else []
    return parts[1].strip() if len(parts) == 2 and parts[0] == "Bearer" else None
