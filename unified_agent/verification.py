from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import Task
from .registry import Capability


class VerificationStatus(str, Enum):
    PASSED = "passed"
    PARTIAL = "partial"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


@dataclass
class VerificationCheck:
    name: str
    passed: bool
    score: float
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "score": self.score,
            "failures": self.failures,
            "warnings": self.warnings,
        }


@dataclass
class VerificationResult:
    status: VerificationStatus
    passed: bool
    confidence: float
    evidence: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[VerificationCheck] = field(default_factory=list)
    requires_human_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "passed": self.passed,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "failures": self.failures,
            "warnings": self.warnings,
            "checks": [check.to_dict() for check in self.checks],
            "requires_human_review": self.requires_human_review,
        }


class VerificationEngine:
    """Deterministic result QA layer.

    It validates the parts that can be verified mechanically and explicitly
    reports unsupported constraints instead of pretending they were checked.
    """

    _WEIGHTS = {"schema": 0.25, "evidence": 0.30, "constraints": 0.30, "consistency": 0.15}

    def verify(
        self,
        task: Task,
        capability: Capability,
        output: Any,
        *,
        evidence: list[dict[str, Any]] | None = None,
    ) -> VerificationResult:
        evidence_items = list(evidence if evidence is not None else task.evidence)
        checks = [
            self._schema_check(capability.output_schema, output),
            self._evidence_check(task, evidence_items),
            self._constraint_check(task, output),
            self._consistency_check(output),
        ]
        failures = [failure for check in checks for failure in check.failures]
        warnings = [warning for check in checks for warning in check.warnings]
        confidence = round(sum(self._WEIGHTS[check.name] * check.score for check in checks), 3)

        hard_fail = any(not check.passed for check in checks if check.name in {"schema", "evidence", "constraints", "consistency"})
        review = bool(warnings) or confidence < 0.75
        if hard_fail:
            status = VerificationStatus.FAILED
        elif review:
            status = VerificationStatus.NEEDS_REVIEW
        else:
            status = VerificationStatus.PASSED

        return VerificationResult(
            status=status,
            passed=status == VerificationStatus.PASSED,
            confidence=confidence,
            evidence=evidence_items,
            failures=failures,
            warnings=warnings,
            checks=checks,
            requires_human_review=review or hard_fail,
        )

    def _schema_check(self, schema: dict[str, Any], output: Any) -> VerificationCheck:
        if not schema:
            return VerificationCheck("schema", True, 1.0)
        failures: list[str] = []
        expected = schema.get("type")
        if expected and not self._matches_type(output, expected):
            failures.append(f"Output must have type {expected}")
        if isinstance(output, dict):
            for key in schema.get("required", []):
                if key not in output:
                    failures.append(f"Missing required output field: {key}")
            for key, spec in schema.get("properties", {}).items():
                if key in output and isinstance(spec, dict) and spec.get("type") and not self._matches_type(output[key], spec["type"]):
                    failures.append(f"Output field {key!r} must have type {spec['type']}")
        score = 1.0 if not failures else 0.0
        return VerificationCheck("schema", not failures, score, failures=failures)

    @staticmethod
    def _matches_type(value: Any, expected: str) -> bool:
        return {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(expected, True)

    def _evidence_check(self, task: Task, evidence: list[dict[str, Any]]) -> VerificationCheck:
        required = bool(task.constraints.get("requires_evidence", False))
        if not evidence:
            if required:
                return VerificationCheck("evidence", False, 0.0, failures=["Evidence is required but none was supplied"])
            return VerificationCheck("evidence", True, 1.0)
        failures: list[str] = []
        qualities: list[float] = []
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                failures.append(f"Evidence item {index} is not an object")
                continue
            if not item.get("source"):
                failures.append(f"Evidence item {index} has no source")
            if not any(item.get(key) is not None for key in ("claim", "content", "value", "excerpt")):
                failures.append(f"Evidence item {index} has no claim/content/value/excerpt")
            quality = item.get("quality", 1.0)
            if not isinstance(quality, (int, float)) or not 0 <= quality <= 1:
                failures.append(f"Evidence item {index} has invalid quality")
            else:
                qualities.append(float(quality))
        score = 0.0 if failures else (sum(qualities) / len(qualities) if qualities else 0.0)
        return VerificationCheck("evidence", not failures, score, failures=failures)

    def _constraint_check(self, task: Task, output: Any) -> VerificationCheck:
        constraints = task.constraints
        failures: list[str] = []
        warnings: list[str] = []
        if not isinstance(output, dict):
            if constraints:
                warnings.append("Structured constraints could not be evaluated because output is not an object")
            return VerificationCheck("constraints", not warnings, 0.75 if warnings else 1.0, warnings=warnings)

        required_keys = constraints.get("required_keys", [])
        for key in required_keys:
            if key not in output:
                failures.append(f"Required output key missing: {key}")

        for key, limit in constraints.get("max", {}).items():
            value = output.get(key)
            if value is None:
                failures.append(f"Cannot verify max constraint for missing field: {key}")
            elif isinstance(value, (int, float)) and value > limit:
                failures.append(f"{key} exceeds maximum {limit}")

        for key, limit in constraints.get("min", {}).items():
            value = output.get(key)
            if value is None:
                failures.append(f"Cannot verify min constraint for missing field: {key}")
            elif isinstance(value, (int, float)) and value < limit:
                failures.append(f"{key} is below minimum {limit}")

        for key, expected in constraints.get("equals", {}).items():
            if output.get(key) != expected:
                failures.append(f"{key} does not equal the required value")

        supported = {"requires_evidence", "required_keys", "max", "min", "equals"}
        unsupported = set(constraints) - supported
        if unsupported:
            warnings.append("Some constraints are not machine-verifiable: " + ", ".join(sorted(unsupported)))
        score = 0.0 if failures else (0.85 if warnings else 1.0)
        return VerificationCheck("constraints", not failures, score, failures=failures, warnings=warnings)

    def _consistency_check(self, output: Any) -> VerificationCheck:
        if not isinstance(output, dict):
            return VerificationCheck("consistency", True, 1.0)
        failures: list[str] = []
        claims = output.get("claims")
        if isinstance(claims, list):
            seen: dict[str, Any] = {}
            for item in claims:
                if not isinstance(item, dict) or "name" not in item:
                    continue
                name = str(item["name"])
                value = item.get("value")
                if name in seen and seen[name] != value:
                    failures.append(f"Conflicting values for claim {name!r}")
                seen[name] = value
        return VerificationCheck("consistency", not failures, 0.0 if failures else 1.0, failures=failures)
