from __future__ import annotations

import json
import subprocess
from typing import Any


class TidasSdkValidationError(RuntimeError):
    """Raised when the TIDAS SDK validation bridge cannot complete."""


_ENTITY_TYPE_ALIASES = {
    "model": "lifeCycleModel",
    "lifecyclemodel": "lifeCycleModel",
    "life-cycle-model": "lifeCycleModel",
    "life_cycle_model": "lifeCycleModel",
}

_NODE_VALIDATE_SCRIPT = r"""
import { createRequire } from 'node:module';

const require = createRequire(process.cwd() + '/');

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

async function loadSdkCore() {
  const moduleName = process.env.TIDAS_SDK_CORE_MODULE || '@tiangong-lca/tidas-sdk/core';
  try {
    return await import(moduleName);
  } catch (importError) {
    try {
      return require(moduleName);
    } catch (requireError) {
      throw importError;
    }
  }
}

function cleanForJson(value) {
  return JSON.parse(
    JSON.stringify(value, (_key, current) => {
      if (current instanceof Error) {
        return {
          name: current.name,
          message: current.message,
          issues: current.issues,
        };
      }
      return current;
    })
  );
}

const request = JSON.parse(await readStdin());
const sdk = await loadSdkCore();

if (typeof sdk.createTidasEntity !== 'function') {
  throw new Error('TIDAS SDK core module does not export createTidasEntity().');
}

const entity = sdk.createTidasEntity(
  request.entityType,
  request.data,
  request.validationConfig
);

if (!entity || typeof entity.validateEnhanced !== 'function') {
  throw new Error('TIDAS SDK entity does not expose validateEnhanced().');
}

const result = entity.validateEnhanced();
process.stdout.write(JSON.stringify(cleanForJson(result)));
"""


def normalize_entity_type(entity_type: str) -> str:
    normalized = entity_type.strip()
    return _ENTITY_TYPE_ALIASES.get(normalized.lower(), normalized)


def validate_enhanced(
    payload: dict[str, Any],
    *,
    entity_type: str,
    mode: str = "strict",
    include_warnings: bool = True,
    timeout: int = 30,
) -> dict[str, Any]:
    """Validate a TIDAS dataset through SDK validateEnhanced()."""

    request = {
        "data": payload,
        "entityType": normalize_entity_type(entity_type),
        "validationConfig": {
            "mode": mode,
            "includeWarnings": include_warnings,
        },
    }

    try:
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", _NODE_VALIDATE_SCRIPT],
            input=json.dumps(request, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        raise TidasSdkValidationError(
            "Node.js is required to call @tiangong-lca/tidas-sdk validateEnhanced()."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise TidasSdkValidationError(
            f"TIDAS SDK validateEnhanced() timed out after {timeout} seconds."
        ) from error

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise TidasSdkValidationError(
            f"TIDAS SDK validateEnhanced() failed: {detail}"
        )

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise TidasSdkValidationError(
            f"TIDAS SDK validateEnhanced() returned invalid JSON: {completed.stdout!r}"
        ) from error
