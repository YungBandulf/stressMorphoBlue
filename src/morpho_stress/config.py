"""Typed configuration loaded from YAML + environment variables.

The config is the single source of truth for network endpoints, sampling cadences,
and market lists. All fetch scripts and modeling code receive a Config instance
rather than reading env vars directly.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class NetworkConfig(BaseModel):
    chain_id: int = 1
    rpc_url: str
    rpc_url_fallback: str | None = None

    @field_validator("rpc_url", "rpc_url_fallback")
    @classmethod
    def expand_env(cls, v: str | None) -> str | None:
        return os.path.expandvars(v) if v else v


class MorphoBlueConfig(BaseModel):
    contract: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")


class SubgraphConfig(BaseModel):
    url: HttpUrl
    api_key: str | None = None

    @field_validator("api_key")
    @classmethod
    def expand_env(cls, v: str | None) -> str | None:
        if v is None:
            return None
        expanded = os.path.expandvars(v)
        # If the env var did not exist, expandvars returns the literal `${...}`;
        # treat that as missing.
        return None if expanded.startswith("${") else expanded


class OneInchConfig(BaseModel):
    api_url: HttpUrl
    api_key: str | None = None

    @field_validator("api_key")
    @classmethod
    def expand_env(cls, v: str | None) -> str | None:
        if v is None:
            return None
        expanded = os.path.expandvars(v)
        return None if expanded.startswith("${") else expanded


class SamplingConfig(BaseModel):
    market_state_period_blocks: int = Field(gt=0)
    oracle_price_period_blocks: int = Field(gt=0)
    position_snapshot_period_blocks: int = Field(gt=0)


class RangeConfig(BaseModel):
    start_ts: datetime
    end_ts: datetime

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if self.end_ts <= self.start_ts:
            raise ValueError("end_ts must be after start_ts")
        return self


class Config(BaseModel):
    network: NetworkConfig
    morpho_blue: MorphoBlueConfig
    subgraph: SubgraphConfig
    oneinch: OneInchConfig | None = None
    sampling: SamplingConfig
    range: RangeConfig
    markets: list[str] = Field(default_factory=list)

    @field_validator("markets")
    @classmethod
    def validate_market_ids(cls, v: list[str]) -> list[str]:
        for mid in v:
            if not (mid.startswith("0x") and len(mid) == 66):
                raise ValueError(f"Invalid Morpho market id (expect 32-byte hex): {mid}")
        return v

    @classmethod
    def load(cls, path: str | Path = "config.local.yaml") -> "Config":
        """Load config from YAML, falling back to template if local override missing."""
        path = Path(path)
        if not path.exists():
            template = Path("config.yaml")
            if template.exists():
                raise FileNotFoundError(
                    f"{path} not found. Copy {template} to {path} and edit local secrets."
                )
            raise FileNotFoundError(f"Neither {path} nor config.yaml found.")
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)
