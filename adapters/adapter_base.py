from abc import ABC, abstractmethod
from typing import Any, Dict

class AdapterBase(ABC):

    @abstractmethod
    def validate_manifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def validate_input(self, manifest: Dict[str, Any], input_json: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def execute_sync(self, manifest: Dict[str, Any], run_id: str, input_json: Dict[str, Any], exec_opts: Dict[str, Any]) -> Dict[str, Any]:
        ...
