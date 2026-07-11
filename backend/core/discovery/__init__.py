"""
core/discovery — discovery-channel orchestrators + the channel registry.

An orchestrator does the I/O for one channel (parse a file, call an admin API,
read logs), runs the PURE normalizer from engine/collectors, and merges the
result via merge.merge_discovered_assets. Every channel feeds the SAME ai_assets
registry → cure engine → statutory artifacts, unchanged.

COLLECTORS is the single swap point (project principle #3): adding a channel adds
one entry here plus one normalizer, one orchestrator, one schema alias block, and
one thin route. Nothing downstream of the registry changes.
"""

# channel key -> {provenance, module, entry}. Looked up + lazy-imported by routes.
COLLECTORS = {
    "procurement": {
        "provenance": "discovered_procurement",
        "module": "core.discovery.procurement_source",
        "entry": "run_procurement_discovery",
    },
    "agenda": {
        "provenance": "discovered_agenda",
        "module": "core.discovery.agenda_source",
        "entry": "run_agenda_discovery",
    },
    # "oauth":   {...}  ← flagship, next
    # "network": {...}
}
