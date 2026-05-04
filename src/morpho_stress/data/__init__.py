"""Data acquisition layer for Morpho Blue stress testing.

This module is the single boundary between vendor APIs (RPC, subgraph, DEX)
and the on-disk Parquet cache that downstream modeling code consumes.

Usage:
    from morpho_stress.data import Config, RPCClient, write_parquet

Modeling code never imports submodules of `data`; it reads exclusively from
``data/cache/*.parquet`` via DuckDB.
"""

from morpho_stress.config import Config
from morpho_stress.data.manifest import FileEntry, Manifest, RunEntry, ValidationResult
from morpho_stress.data.rpc import RPCClient, safe_block
from morpho_stress.data.schemas import REGISTRY, get_schema
from morpho_stress.data.storage import read_parquet, write_parquet
from morpho_stress.data.subgraph import SubgraphClient, SubgraphError

__all__ = [
    "Config",
    "FileEntry",
    "Manifest",
    "RPCClient",
    "REGISTRY",
    "RunEntry",
    "SubgraphClient",
    "SubgraphError",
    "ValidationResult",
    "get_schema",
    "read_parquet",
    "safe_block",
    "write_parquet",
]
