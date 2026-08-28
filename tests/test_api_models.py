from garmin_sync.api_models import exported_schema


def test_exported_api_schema_contains_resolvable_shared_models() -> None:
    schema = exported_schema()
    definitions = schema["$defs"]
    assert "ApiEnvelope" in definitions
    assert "ApiError" in definitions
    assert definitions["ApiEnvelope"]["properties"]["error"]["anyOf"][0]["$ref"] == (
        "#/$defs/ApiError"
    )
