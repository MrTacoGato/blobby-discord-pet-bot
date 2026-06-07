"""
DynamoDB storage (single-table design).

Layout:
    pk = "GUILD#<guild_id>"
    sk = "PET"            -> the one communal pet for that server
    sk = "USER#<user_id>" -> each member's contribution + streak

All functions here are synchronous (boto3 is sync). The bot calls them via
asyncio.to_thread so they never block the event loop.

Note on concurrency: this uses simple read-modify-write (last write wins),
which is fine for a friend-sized server. For higher contention you'd switch
the counters to atomic DynamoDB UpdateExpressions (ADD) or conditional writes.
"""

from decimal import Decimal

import boto3

import config


_table = None


def _get_table():
    global _table
    if _table is None:
        kwargs = {"region_name": config.AWS_REGION}
        if config.DYNAMODB_ENDPOINT:
            kwargs["endpoint_url"] = config.DYNAMODB_ENDPOINT
        resource = boto3.resource("dynamodb", **kwargs)
        _table = resource.Table(config.TABLE_NAME)
    return _table


def ensure_table():
    """Create the table if it doesn't exist. Handy for local dev.

    In production you'd normally create this via the console / CDK / Terraform
    and skip calling this, but it's safe to leave on (it no-ops if present).
    """
    kwargs = {"region_name": config.AWS_REGION}
    if config.DYNAMODB_ENDPOINT:
        kwargs["endpoint_url"] = config.DYNAMODB_ENDPOINT
    resource = boto3.resource("dynamodb", **kwargs)
    client = resource.meta.client

    existing = client.list_tables().get("TableNames", [])
    if config.TABLE_NAME in existing:
        return

    resource.create_table(
        TableName=config.TABLE_NAME,
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=config.TABLE_NAME)


# --------------------------------------------------------------------------
# Number conversion (DynamoDB stores numbers as Decimal)
# --------------------------------------------------------------------------
def _to_dynamo(obj):
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return Decimal(str(round(obj, 4)))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _from_dynamo(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _from_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_dynamo(v) for v in obj]
    return obj


def _pet_key(guild_id: int):
    return {"pk": f"GUILD#{guild_id}", "sk": "PET"}


def _user_key(guild_id: int, user_id: int):
    return {"pk": f"GUILD#{guild_id}", "sk": f"USER#{user_id}"}


def _collection_key(guild_id: int):
    return {"pk": f"GUILD#{guild_id}", "sk": "COLLECTION"}


# --------------------------------------------------------------------------
# Pet
# --------------------------------------------------------------------------
def load_pet(guild_id: int):
    resp = _get_table().get_item(Key=_pet_key(guild_id))
    item = resp.get("Item")
    return _from_dynamo(item) if item else None


def save_pet(guild_id: int, pet: dict):
    item = {**_pet_key(guild_id), **pet}
    _get_table().put_item(Item=_to_dynamo(item))


# --------------------------------------------------------------------------
# Shared collection (one record per server, sk = "COLLECTION")
# --------------------------------------------------------------------------
def load_collection(guild_id: int):
    resp = _get_table().get_item(Key=_collection_key(guild_id))
    item = resp.get("Item")
    return _from_dynamo(item) if item else None


def save_collection(guild_id: int, collection: dict):
    item = {**_collection_key(guild_id), **collection}
    _get_table().put_item(Item=_to_dynamo(item))


# --------------------------------------------------------------------------
# User
# --------------------------------------------------------------------------
def new_user() -> dict:
    return {"xp_contributed": 0, "last_xp_ts": 0, "last_checkin": None, "streak": 0}


def load_user(guild_id: int, user_id: int):
    resp = _get_table().get_item(Key=_user_key(guild_id, user_id))
    item = resp.get("Item")
    return _from_dynamo(item) if item else None


def save_user(guild_id: int, user_id: int, user: dict):
    item = {**_user_key(guild_id, user_id), **user}
    _get_table().put_item(Item=_to_dynamo(item))
