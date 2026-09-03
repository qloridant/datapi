from abc import ABC, abstractmethod
from typing import Any, Dict

class AdapterBase(ABC):
    @abstractmethod
    def identify(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    def validate_manifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def validate_input(self, manifest: Dict[str, Any], input_json: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def prepare(self, manifest: Dict[str, Any], run_id: str, storage: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def execute_sync(self, manifest: Dict[str, Any], run_id: str, input_json: Dict[str, Any], exec_opts: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def execute_async(self, manifest: Dict[str, Any], run_id: str, input_json: Dict[str, Any], exec_opts: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def cancel(self, job_id: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def cleanup(self, run_id: str) -> Dict[str, Any]:
        ...
