from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Capability:
    id: str
    name: str
    category: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    execution_type: str = "provider"
    cost: str = "unknown"
    latency: str = "unknown"
    risk: str = "low"
    requires_confirmation: bool = False
    supports_streaming: bool = False
    supports_async: bool = False
    supports_resume: bool = False
    supports_cancellation: bool = False
    supports_verification: bool = False
    availability: str = "unknown"
    fallbacks: list[str] = field(default_factory=list)


class Provider(Protocol):
    id: str
    capabilities: list[str]

    def is_available(self) -> bool: ...
    def execute(self, task: Any, capability: Capability) -> Any: ...


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._providers: dict[str, Provider] = {}

    def register_capability(self, capability: Capability) -> None:
        if capability.id in self._capabilities:
            raise ValueError(f"Capability already registered: {capability.id}")
        self._capabilities[capability.id] = capability

    def register_provider(self, provider: Provider) -> None:
        if provider.id in self._providers:
            raise ValueError(f"Provider already registered: {provider.id}")
        self._providers[provider.id] = provider

    def get_capability(self, capability_id: str) -> Capability:
        return self._capabilities[capability_id]

    def providers_for(self, capability_id: str) -> list[Provider]:
        return [provider for provider in self._providers.values() if capability_id in provider.capabilities and provider.is_available()]

    def list_capabilities(self) -> list[Capability]:
        return list(self._capabilities.values())
