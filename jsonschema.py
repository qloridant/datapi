class ValidationError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message

def _check_type(value, expected):
    if expected == "number":
        return isinstance(value, (int, float))
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True

def validate(instance, schema):
    # Minimal validator: supports required and simple type checks in properties
    if not isinstance(schema, dict):
        return True
    req = schema.get("required", []) or []
    for key in req:
        if key not in instance:
            raise ValidationError(f"'{key}' is a required property")
    props = schema.get("properties", {}) or {}
    for k, spec in props.items():
        if k in instance and "type" in spec:
            typ = spec["type"]
            # handle union types like ["number", "null"]
            if isinstance(typ, list):
                ok = any((_check_type(instance[k], t) or (t == "null" and instance[k] is None)) for t in typ)
            else:
                ok = (_check_type(instance[k], typ) or (typ == "null" and instance[k] is None))
            if not ok:
                raise ValidationError(f"property '{k}' is not of type {typ}")
    return True
