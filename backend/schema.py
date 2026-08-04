TABLE_NAME = "shipments"

# name -> short description, used to build the schema block in the prompt
COLUMNS = {
    "shipment_id": "unique id of the shipment (text)",
    "origin": "standardized origin city (text)",
    "destination": "standardized destination city (text)",
    "route": "origin-destination code, e.g. MUM-DEL (text)",
    "ship_date": "date shipment left origin, ISO format (text/date)",
    "delivery_date": "actual delivery date, ISO format, NULL if not yet delivered",
    "expected_delivery_date": "promised delivery date, ISO format",
    "status": "Delivered / In Transit / Delayed (text)",
    "delay_days": "delivery_date - expected_delivery_date in days, NULL if undelivered",
    "is_delayed": "1 if delay_days > 0 else 0",
}

ALLOWED_COLUMNS = set(COLUMNS.keys())


def schema_prompt_block() -> str:
    lines = [f"Table: {TABLE_NAME}", "Columns:"]
    for name, desc in COLUMNS.items():
        lines.append(f"  - {name}: {desc}")
    return "\n".join(lines)
