"""Read process and lifecycle-model datasets from Tiangong."""

from __future__ import annotations

from typing import Any

from .client import TiangongAPIClient, TiangongAPIError
from .models import DatasetType

PROCESS_COLUMNS = (
    "id,version,json,modified_at,state_code,rule_verification,team_id,reviews"
)
MODEL_COLUMNS = (
    "id,version,json,json_tg,modified_at,state_code,rule_verification,team_id,reviews"
)


class DatasetAPI:
    """Read-only access to auditable Tiangong datasets."""

    def __init__(self, client: TiangongAPIClient):
        self.client = client

    def get_dataset(
        self,
        dataset_id: str,
        version: str,
        dataset_type: DatasetType,
    ) -> dict[str, Any]:
        table = "processes" if dataset_type == DatasetType.PROCESS else "lifecyclemodels"
        columns = PROCESS_COLUMNS if dataset_type == DatasetType.PROCESS else MODEL_COLUMNS
        rows = self.client.select(
            table,
            columns=columns,
            filters={"id": f"eq.{dataset_id}", "version": f"eq.{version}"},
            limit=1,
        )
        if not rows:
            raise TiangongAPIError(
                f"{dataset_type.value} dataset not found: {dataset_id} {version}"
            )
        return rows[0]

    def get_process(self, dataset_id: str, version: str) -> dict[str, Any]:
        return self.get_dataset(dataset_id, version, DatasetType.PROCESS)

    def get_model(self, dataset_id: str, version: str) -> dict[str, Any]:
        return self.get_dataset(dataset_id, version, DatasetType.MODEL)

    def resolve_dataset(self, dataset_id: str, version: str) -> dict[str, Any]:
        """Identify a task dataset and return its platform payload."""
        model_rows = self.client.select(
            "lifecyclemodels",
            columns=MODEL_COLUMNS,
            filters={"id": f"eq.{dataset_id}", "version": f"eq.{version}"},
            limit=1,
        )
        if model_rows:
            return {"dataset_type": DatasetType.MODEL.value, "data": model_rows[0]}
        return {
            "dataset_type": DatasetType.PROCESS.value,
            "data": self.get_process(dataset_id, version),
        }
