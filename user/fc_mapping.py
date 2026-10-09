"""
France Connect Mapping Engine

This module provides the core functionality for mapping France Connect claims
to algorithm input fields using the hybrid approach (global defaults + per-algorithm overrides).

Usage:
    from user.fc_mapping import FCMappingEngine
    
    engine = FCMappingEngine()
    
    # Load FC claims (from OIDC userinfo)
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
    
    # Get algorithm manifest
    manifest = {...}
    
    # Generate input payload with FC data pre-filled
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


class FCMappingEngine:
    """
    Engine for mapping France Connect claims to algorithm inputs.
    
    Supports:
    - Default mappings from config/franceconnect_mapping.yaml
    - Per-algorithm mapping overrides
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
    
    def _apply_transform(
        self, 
        value: Any, 
        transform_name: str,
        **kwargs: Any
    ) -> Any:
        """
        Apply a transformation function to a value.
        
        Args:
            value: The input value
            transform_name: Name of the transform function
            **kwargs: Additional arguments for the transform
        
        Returns:
            The transformed value
        
        Raises:
            MissingTransformError: If transform doesn't exist
        """
        if transform_name not in self._transforms:
            raise MissingTransformError(
                f"Transform function '{transform_name}' not found"
            )
        
        transform_func = self._transforms[transform_name]
        
        try:
            # Handle both positional and keyword arguments
            if kwargs:
                return transform_func(value, **kwargs)
            else:
                return transform_func(value)
        except Exception as e:
            raise FCMappingError(
                f"Failed to apply transform '{transform_name}': {str(e)}"
            )
    
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
            raw_value = self._apply_transform(raw_value, transform_name)
        
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
                fc_path, _ = self._parse_mapping_value(mapping, fc_claims)
                if fc_path:
                    value = self._resolve_fc_path(fc_claims, fc_path)
                    if value is not None:
                        # Apply transform if configured in the mapping
                        if isinstance(mapping, str) and "|" in mapping:
                            _, transform_part = mapping.split("|", 1)
                            if "transform:" in transform_part:
                                transform_name = transform_part.split("transform:")[1].strip()
                                value = self._apply_transform(value, transform_name)
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
        
        # Get the algorithm's FC mapping configuration
        fc_mapping = manifest.get("franceconnect_mapping", {})
        mappings = fc_mapping.get("mappings", {})
        
        # Also check for package-level mapping if this is from a package
        if "algorithms" in manifest:
            # This is a package manifest - use its mapping as fallback
            package_mapping = manifest.get("franceconnect_mapping", {})
            package_mappings = package_mapping.get("mappings", {})
            # Merge: algorithm mappings override package mappings
            effective_mappings = {**package_mappings, **mappings}
        else:
            effective_mappings = mappings
        
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
        Get metadata for all fields that can be mapped from FC.
        
        Useful for building the input form with pre-filled values and labels.
        
        Args:
            fc_claims: Raw France Connect claims
            manifest: The algorithm manifest
        
        Returns:
            List of field metadata dicts
        """
        fc_mapping = manifest.get("franceconnect_mapping", {})
        mappings = fc_mapping.get("mappings", {})
        
        input_schema = manifest.get("input_schema", {})
        
        fields = []
        
        # Process each mapping
        for input_path, mapping_config in mappings.items():
            # Get value from FC
            value, extended_config = self._get_mapping_value(mapping_config, fc_claims)
            
            # Get schema
            field_schema = self._get_nested_schema(input_schema, input_path)
            
            field_info = {
                "path": input_path,
                "value": value,
                "has_fc_value": value is not None,
                "schema": field_schema or {},
                "label": extended_config.get("label", input_path) if extended_config else input_path,
                "required": True,  # Will be determined below
                "type": field_schema.get("type", "unknown") if field_schema else "unknown",
                "default": extended_config.get("default") if extended_config else None
            }
            
            # Determine if required
            if extended_config and "required" in extended_config:
                field_info["required"] = extended_config["required"]
            elif field_schema:
                field_info["required"] = field_schema.get("required", False)
                if isinstance(field_info["required"], list):
                    field_info["required"] = input_path in field_info["required"]
            
            fields.append(field_info)
        
        # Sort fields: required first, then alphabetical
        fields.sort(key=lambda f: (not f["required"], f["path"]))
        
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
        Validate the franceconnect_mapping section of a manifest.
        
        Args:
            manifest: The manifest to validate
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        fc_mapping = manifest.get("franceconnect_mapping", {})
        
        if not isinstance(fc_mapping, dict):
            errors.append("franceconnect_mapping must be an object")
            return errors
        
        mappings = fc_mapping.get("mappings", {})
        if not isinstance(mappings, dict):
            errors.append("franceconnect_mapping.mappings must be an object")
            return errors
        
        # Check each mapping value
        for path, value in mappings.items():
            if value is None:
                continue  # Valid: manual input
            
            if isinstance(value, str):
                # Check if it references a default mapping
                if value.startswith("$default."):
                    default_key = value[9:]
                    if default_key not in self._default_mappings:
                        errors.append(f"Mapping '{path}' references unknown default '{default_key}'")
                # Otherwise it's an FC path - we can't validate it exists here
            elif isinstance(value, dict):
                # Extended mapping
                if "transform" in value:
                    transform_name = value["transform"]
                    if transform_name not in self._transforms:
                        errors.append(
                            f"Mapping '{path}' uses unknown transform '{transform_name}'"
                        )
            else:
                errors.append(f"Mapping '{path}' has invalid type: {type(value)}")
        
        return errors


# Global instance for convenience
_fc_mapping_engine: Optional[FCMappingEngine] = None


def get_fc_mapping_engine() -> FCMappingEngine:
    """Get or create the global FCMappingEngine instance."""
    global _fc_mapping_engine
    if _fc_mapping_engine is None:
        _fc_mapping_engine = FCMappingEngine()
    return _fc_mapping_engine
