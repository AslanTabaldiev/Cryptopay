"""Понятные русские сообщения вместо стандартных английских ошибок валидации Pydantic."""

from __future__ import annotations

FIELD_NAMES = {
    "amount_eth": "Сумма",
    "description": "Описание",
    "order_id": "Номер заказа",
    "ttl_minutes": "Срок действия",
    "tx_hash": "Хэш транзакции",
    "limit": "Лимит",
}


def _message(error: dict) -> str:
    kind = error.get("type", "")
    ctx = error.get("ctx") or {}
    if kind == "missing":
        return "обязательное поле"
    if kind == "greater_than":
        return f"должно быть больше {ctx.get('gt')}"
    if kind == "greater_than_equal":
        return f"должно быть не меньше {ctx.get('ge')}"
    if kind == "less_than_equal":
        return f"должно быть не больше {ctx.get('le')}"
    if kind == "less_than":
        return f"должно быть меньше {ctx.get('lt')}"
    if kind == "string_too_short":
        return "не может быть пустым"
    if kind == "string_too_long":
        return f"слишком длинное (максимум {ctx.get('max_length')} символов)"
    if kind in {"decimal_parsing", "int_parsing", "float_parsing", "decimal_type", "int_type"}:
        return "должно быть числом"
    if kind in {"json_invalid", "model_attributes_type", "dict_type"}:
        return "некорректный формат запроса"
    return "некорректное значение"


def describe_validation_errors(errors: list[dict]) -> str:
    parts = []
    for error in errors:
        field = next((str(p) for p in reversed(error.get("loc", ())) if p not in ("body", "query", "path")), "")
        name = FIELD_NAMES.get(field, field)
        parts.append(f"{name}: {_message(error)}" if name else _message(error))
    return "; ".join(parts) or "Некорректный запрос"
