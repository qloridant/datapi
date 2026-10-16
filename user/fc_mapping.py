"""
France Connect Mapping Engine

This module provides the core functionality for mapping France Connect claims
to algorithm input fields.

The mapping is declared directly on each ``input_schema`` property, via the
``franceconnect`` keyword (see ``FC_MAPPING_KEYWORD``) — there is no separate
manifest block. A property's value can be:

- ``"$default.<name>"`` — a reference to a default mapping from
  ``config/franceconnect_mapping.yaml`` (shared defaults, overridable),
- a direct FC claim path (e.g. ``"birthdate"`` or ``"address.postal_code"``),
- ``null`` — the field must be provided manually,
- an extended object (``{"source": ..., "transform": ..., "label": ...}``).

Properties without the keyword are never prefilled from France Connect.

Usage:
    from user.fc_mapping import FCMappingEngine

    engine = FCMappingEngine()

    fc_claims = {
        "sub": "123456",
        "given_name": "Jean",
        "family_name": "Dupont",
        "birthdate": "1990-05-15",
        "email": "jean.dupont@example.com",
        "address": {
            "postal_code": "75001",
            "city": "Paris"
        }
    }

    manifest = {...}  # input_schema properties carry "franceconnect" keys

    input_payload, missing_fields, consent_fields = engine.generate_input_payload(
        fc_claims, manifest
    )
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
import yaml


class FCMappingError(Exception):
    """Base exception for France Connect mapping errors."""
    pass


class MissingTransformError(FCMappingError):
    """Raised when a referenced transform function doesn't exist."""
    pass


class InvalidMappingError(FCMappingError):
    """Raised when a mapping configuration is invalid."""
    pass


# JSON Schema keyword, on each input_schema property, declaring its France
# Connect mapping. Unknown to JSON Schema validators, which simply ignore it.
FC_MAPPING_KEYWORD = "franceconnect"


def extract_mappings(input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Collect the France Connect mappings declared inside an input_schema.

    Walks the schema's ``properties`` recursively and returns a dict keyed by
    dotted property path (e.g. ``data.date_naissance``), whose values are the
    property's ``franceconnect`` mapping. Properties without the keyword are
    skipped — they are never prefilled from France Connect.

    Args:
        input_schema: The manifest's input_schema

    Returns:
        Dict of {dotted_path: mapping_config}
    """
    mappings: Dict[str, Any] = {}

    def _walk(schema: Any, prefix: str) -> None:
        if not isinstance(schema, dict):
            return
        for name, prop in (schema.get("properties") or {}).items():
            path = f"{prefix}.{name}" if prefix else name
            if isinstance(prop, dict):
                if FC_MAPPING_KEYWORD in prop:
                    mappings[path] = prop[FC_MAPPING_KEYWORD]
                _walk(prop, path)

    _walk(input_schema, "")
    return mappings


class FCMappingEngine:
    """
    Engine for mapping France Connect claims to algorithm inputs.

    Supports:
    - Default mappings from config/franceconnect_mapping.yaml
    - Per-property mappings declared directly on input_schema (franceconnect keyword)
    - Transformation functions
    - Consent tracking
    """
    
    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "franceconnect_mapping.yaml"
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the mapping engine.
        
        Args:
            config_path: Path to YAML config file. If None, uses default path.
        """
        self.config_path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
        self._config: Optional[Dict[str, Any]] = None
        self._transforms: Optional[Dict[str, Callable]] = None
        self._default_mappings: Optional[Dict[str, Any]] = None
        
        # Load configuration
        self._load_config()
        
    def _load_config(self) -> None:
        """Load and parse the YAML configuration file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"France Connect mapping config not found at {self.config_path}"
            )
        
        with open(self.config_path, 'r') as f:
            self._config = yaml.safe_load(f)
        
        # Extract default mappings
        self._default_mappings = self._config.get("default_mappings", {})
        
        # Load and compile transformation functions
        self._transforms = {}
        transforms_config = self._config.get("transforms", {})
        for name, transform_def in transforms_config.items():
            self._transforms[name] = self._compile_transform(name, transform_def)
    
    def _compile_transform(self, name: str, transform_def: Dict[str, Any]) -> Callable:
        """
        Compile a transformation function from its YAML definition.
        
        The transform_def should have a 'code' key with Python code.
        """
        code = transform_def.get("code", "")
        if not code:
            raise InvalidMappingError(f"Transform '{name}' has no code")
        
        # Create a namespace for the function
        namespace: Dict[str, Any] = {}
        
        try:
            # Exec the code to define the transform function
            exec(code, namespace)
            transform_func = namespace.get("transform")
            
            if not callable(transform_func):
                raise InvalidMappingError(
                    f"Transform '{name}' does not define a callable 'transform' function"
                )
            
            return transform_func
        except Exception as e:
            raise InvalidMappingError(
                f"Failed to compile transform '{name}': {str(e)}"
            )
    
    def _resolve_fc_path(self, fc_claims: Dict[str, Any], path: str) -> Optional[Any]:
        """
        Resolve a dot-notation path in FC claims.
        
        Example: 'address.postal_code' -> fc_claims['address']['postal_code']
        
        Args:
            fc_claims: The raw France Connect claims
            path: Dot-notation path (e.g., 'address.postal_code')
        
        Returns:
            The value at the path, or None if not found
        """
        if not path:
            return None
        
        parts = path.split(".")
        current = fc_claims
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                if 0 <= index < len(current):
                    current = current[index]
                else:
                    return None
            else:
                return None
        
        return current
   
    
    def _parse_mapping_value(
        self, 
        value: Any,
        fc_claims: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Parse a mapping value which can be:
        - A string (FC path or default reference)
        - null (manual input required)
        - An object with source, transform, etc.
        
        Returns:
            Tuple of (fc_path_or_none, extended_config_or_none)
        """
        if value is None:
            return None, None
        
        if isinstance(value, str):
            # Check if it's a default mapping reference
            if value.startswith("$default."):
                default_key = value[9:]  # Remove "$default."
                if default_key in self._default_mappings:
                    # Recursively parse the default mapping
                    return self._parse_mapping_value(
                        self._default_mappings[default_key],
                        fc_claims
                    )
                else:
                    raise InvalidMappingError(
                        f"Default mapping '{default_key}' not found"
                    )
            # Otherwise it's a direct FC path
            return value, None
        
        if isinstance(value, dict):
            # Extended mapping configuration
            source = value.get("source")
            if source and isinstance(source, str):
                if source.startswith("$default."):
                    default_key = source[9:]
                    if default_key in self._default_mappings:
                        source = self._default_mappings[default_key]
                        if isinstance(source, str):
                            return source, value
                        elif isinstance(source, dict):
                            # Merge with the extended config
                            merged = {**source, **value}
                            if "source" in value:
                                del merged["source"]
                            return merged.get("source"), merged
                return source, value
            return None, value
        
        return None, None
    
    def _get_mapping_value(
        self,
        mapping_config: Any,
        fc_claims: Dict[str, Any]
    ) -> Tuple[Any, Optional[Dict[str, Any]]]:
        """
        Get the value from FC claims based on a mapping configuration.
        
        Returns:
            Tuple of (resolved_value, extended_config)
        """
        fc_path, extended_config = self._parse_mapping_value(mapping_config, fc_claims)
        
        if fc_path is None:
            return None, extended_config
        
        # Resolve the FC path
        raw_value = self._resolve_fc_path(fc_claims, fc_path)
        
        if raw_value is None:
            return None, extended_config
        
        # Apply transform if specified
        if extended_config and "transform" in extended_config:
            transform_name = extended_config["transform"]
            # raw_value = self._apply_transform(raw_value, transform_name)
        
        return raw_value, extended_config
    
    def _set_nested_value(
        self,
        target: Dict[str, Any],
        path: str,
        value: Any
    ) -> None:
        """
        Set a value in a nested dictionary using dot-notation path.
        Creates intermediate dictionaries as needed.
        
        Example: set_nested_value({}, "data.age", 25) -> {"data": {"age": 25}}
        
        Args:
            target: The dictionary to modify
            path: Dot-notation path (e.g., "data.age")
            value: The value to set
        """
        parts = path.split(".")
        current = target
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
            if not isinstance(current, dict):
                raise InvalidMappingError(
                    f"Cannot set nested value at '{part}': parent is not a dict"
                )
        
        current[parts[-1]] = value
    
    def _get_nested_schema(
        self,
        schema: Dict[str, Any],
        path: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the schema definition for a nested path.
        
        Args:
            schema: The JSON schema
            path: Dot-notation path
        
        Returns:
            The schema for that path, or None if not found
        """
        parts = path.split(".")
        current = schema
        
        for part in parts:
            if isinstance(current, dict):
                if "properties" in current and part in current["properties"]:
                    current = current["properties"][part]
                elif part in current:
                    current = current[part]
                else:
                    return None
            else:
                return None
        
        return current
    
    def extract_pivot_data(
        self,
        fc_claims: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract pivot data from France Connect claims.
        
        Pivot data are the core user attributes that are available
        to all algorithms (with user consent).
        
        Args:
            fc_claims: Raw France Connect claims
        
        Returns:
            Dictionary of pivot data
        """
        pivot_config = self._config.get("franceconnect", {}).get("user_data", {}).get("pivot_fields", [])
        
        pivot_data = {}
        for field in pivot_config:
            # Map pivot field name to FC claim path
            if field in self._default_mappings:
                mapping = self._default_mappings[field]
                value, _ = self._get_mapping_value(self._default_mappings[field], fc_claims)
                if value is not None:
                    pivot_data[field] = value
        return pivot_data
    
    def generate_input_payload(
        self,
        fc_claims: Dict[str, Any],
        manifest: Dict[str, Any],
        user_consent: Optional[Dict[str, bool]] = None
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Generate an input payload for an algorithm using France Connect data.
        
        This is the main method that:
        1. Applies default mappings
        2. Applies algorithm-specific overrides
        3. Identifies missing required fields
        4. Identifies fields requiring consent
        
        Args:
            fc_claims: Raw France Connect claims from userinfo
            manifest: The algorithm manifest
            user_consent: Optional dict of user consent per field (field_path -> bool)
        
        Returns:
            Tuple of:
            - input_payload: Dict with pre-filled values from FC
            - missing_fields: List of field configs that are missing and required
            - consent_fields: List of field configs that need consent
        """
        input_payload: Dict[str, Any] = {}
        missing_fields: List[Dict[str, Any]] = []
        consent_fields: List[Dict[str, Any]] = []

        # FC mappings are declared on input_schema properties (franceconnect
        # keyword) — no separate manifest block.
        effective_mappings = extract_mappings(manifest.get("input_schema", {}))
        
        # Process each mapping
        for input_path, mapping_config in effective_mappings.items():
            # Parse the mapping
            value, extended_config = self._get_mapping_value(mapping_config, fc_claims)
            
            # Get schema info for this field (if available)
            input_schema = manifest.get("input_schema", {})
            field_schema = self._get_nested_schema(input_schema, input_path)
            
            # Check consent
            if user_consent is not None:
                # Check if this field or any parent requires consent
                path_parts = input_path.split(".")
                for i in range(len(path_parts)):
                    check_path = ".".join(path_parts[:i+1])
                    if check_path in user_consent:
                        if not user_consent[check_path]:
                            # User hasn't consented to this field
                            consent_fields.append({
                                "path": input_path,
                                "config": extended_config or {},
                                "schema": field_schema or {},
                                "label": extended_config.get("label", input_path) if extended_config else input_path
                            })
                            # Skip adding to payload
                            break
            
            # If we have a value, add it to the payload
            if value is not None:
                self._set_nested_value(input_payload, input_path, value)
            else:
                # Check if this field is required
                is_required = True  # Default to required
                
                if extended_config and "required" in extended_config:
                    is_required = extended_config["required"]
                elif field_schema:
                    # Check schema required
                    if "required" in field_schema and input_path in field_schema["required"]:
                        is_required = True
                    elif field_schema.get("required", False):
                        is_required = True
                
                if is_required:
                    missing_fields.append({
                        "path": input_path,
                        "config": extended_config or {},
                        "schema": field_schema or {},
                        "label": extended_config.get("label", input_path) if extended_config else input_path,
                        "default": extended_config.get("default") if extended_config else None
                    })
        
        return input_payload, missing_fields, consent_fields
    
    def get_field_metadata(
        self,
        fc_claims: Dict[str, Any],
        manifest: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Get metadata for every input field declared in the manifest's
        input_schema -- FC-mapped properties and unmapped ones (context
        parameters, manual fields).

        FC-mapped properties get their value from FC claims (None if the
        claim is absent); unmapped properties get their JSON Schema
        ``default`` if any. The list keeps the schema's declaration order,
        and each field carries a ``group`` (top-level path segment, e.g.
        "data" or "context") so the frontend can render them in separated
        sections. Container objects (properties with sub-properties) are
        recursed into, not emitted as fields themselves.

        Useful for building the input form with pre-filled values and labels.

        Args:
            fc_claims: Raw France Connect claims
            manifest: The algorithm manifest

        Returns:
            List of field metadata dicts
        """
        input_schema = manifest.get("input_schema", {})
        fields: List[Dict[str, Any]] = []

        def _walk(schema: Any, prefix: str, parent_required: List[str]) -> None:
            if not isinstance(schema, dict):
                return
            for name, prop in (schema.get("properties") or {}).items():
                if not isinstance(prop, dict):
                    continue
                path = f"{prefix}.{name}" if prefix else name

                # Container objects are recursed into, not rendered as fields
                if "properties" in prop:
                    _walk(prop, path, prop.get("required") or [])
                    continue

                mapping_config = prop.get(FC_MAPPING_KEYWORD)

                if mapping_config is not None:
                    value, extended_config = self._get_mapping_value(mapping_config, fc_claims)
                    has_fc_value = value is not None
                    default = extended_config.get("default") if extended_config else None
                else:
                    value = prop.get("default")
                    extended_config = None
                    has_fc_value = False
                    default = prop.get("default")

                fields.append({
                    "path": path,
                    "value": value,
                    "has_fc_value": has_fc_value,
                    "schema": prop,
                    "label": (
                        (extended_config or {}).get("label")
                        or prop.get("title")
                        or path
                    ),
                    "required": (
                        name in (parent_required or [])
                        or (extended_config or {}).get("required") is True
                    ),
                    "type": prop.get("type", "unknown"),
                    "default": default,
                    "mapping": mapping_config,
                    "group": prefix or path,
                })

        _walk(input_schema, "", input_schema.get("required") or [])
        return fields
    
    def get_default_mappings(self) -> Dict[str, Any]:
        """Get the default mappings configuration."""
        return self._default_mappings or {}
    
    def get_transform_functions(self) -> Dict[str, str]:
        """Get the list of available transform functions with their descriptions."""
        transforms_config = self._config.get("transforms", {})
        return {
            name: info.get("description", "No description")
            for name, info in transforms_config.items()
        }
    
    def validate_mapping(
        self,
        manifest: Dict[str, Any]
    ) -> List[str]:
        """
        Validate the France Connect mappings declared on a manifest's
        input_schema properties.

        Args:
            manifest: The manifest to validate

        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        mappings = extract_mappings(manifest.get("input_schema", {}))

        # Check each mapping value
        for path, value in mappings.items():
            if value is None:
                continue  # Valid: manual input

            if isinstance(value, str):
                # Check if it references a default mapping
                if value.startswith("$default."):
                    default_key = value[9:]
                    if default_key not in self._default_mappings:
                        errors.append(f"Property '{path}' references unknown default '{default_key}'")
                # Otherwise it's an FC path - we can't validate it exists here
            elif isinstance(value, dict):
                # Extended mapping
                if "transform" in value:
                    transform_name = value["transform"]
                    if transform_name not in self._transforms:
                        errors.append(
                            f"Property '{path}' uses unknown transform '{transform_name}'"
                        )
            else:
                errors.append(f"Property '{path}' has invalid mapping type: {type(value)}")
        
        return errors


# Global instance for convenience
_fc_mapping_engine: Optional[FCMappingEngine] = None


def get_fc_mapping_engine() -> FCMappingEngine:
    """Get or create the global FCMappingEngine instance."""
    global _fc_mapping_engine
    if _fc_mapping_engine is None:
        _fc_mapping_engine = FCMappingEngine()
    return _fc_mapping_engine
