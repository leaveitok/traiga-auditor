"""
engine/collectors — PURE discovery normalizers (storage-agnostic, no I/O).

Each module turns a channel's raw source data into DiscoveredAsset dicts and
resolves identifiers to a canonical tool_id. These never import repositories or
call the network; the orchestrators in core/discovery/ do the I/O and merge.
"""
