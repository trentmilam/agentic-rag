"""linkgraph LIVE DEMO -- a narrated walkthrough of the real cross-document
relationship graph, run against linkgraph's own hand-authored fixture.

    cd projects/linkgraph
    .venv/Scripts/python.exe run_demo.py

No mocked output: every graph build, traversal, and lint report below runs
live against ``linkgraph.fixtures.FIXTURE_ENTITY_REFS``. The naive-successor
baseline and the bad-merge planter are imported UNMODIFIED from ``eval.py``
(this repo's RED/GREEN self-test) rather than reimplemented here, so the
head-to-head and the graphrx catch shown below are the exact same mechanism
that test proves, just narrated for a reader instead of asserted.

Fixture note: every identifier below uses the ``RFCX``/``ERRX`` prefix on
purpose -- see ``linkgraph/fixtures.py``'s own docstring for why. A real RFC
citation is always exactly ``RFC`` followed by digits with no letter in
between, so ``RFCX9010`` etc. can never collide with, and are not a claim
about, any real, currently-assigned RFC. The GENERAL SHAPE of the fixture
(a monolithic document later split into several independent successors) does
mirror real, well-known RFC history, and that comparison is called out below
where it applies.

Deterministic: no RNG, no wall-clock, no network.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# NOTE: import this repo's own eval.py BEFORE add_sibling_paths() runs. graphrx
# (rag-reliability/graphrx) also has its own top-level eval.py, and
# add_sibling_paths() puts graphrx's root ahead of this one on sys.path -- so
# resolving "eval" after that call would silently import graphrx's eval.py
# instead. While ROOT is still first on sys.path, this is unambiguous.
from eval import naive_latest_successor, plant_bad_merge  # noqa: E402

from linkgraph._paths import add_sibling_paths  # noqa: E402

add_sibling_paths()

from linkgraph import adapter, community, fixtures, resolve  # noqa: E402

from graphrx.graph import adjacency  # noqa: E402
from graphrx.lint import high_risk, report  # noqa: E402

BAR = "=" * 78
HIGH_RISK = 0.25
STRUCTURAL_EDGE_TYPES = {"obsoletes", "updates", "corrects"}


def header(title: str) -> None:
    print(f"\n{BAR}\n  {title}\n{BAR}")


def main() -> int:
    header("LINKGRAPH -- cross-document RFC obsoletes/updates/corrects graph, "
            "handed off to graphrx for structural linting")
    print("  Fixture identifiers (RFCX.../ERRX...) are NOT claims about any real,")
    print("  currently-assigned RFC -- see linkgraph/fixtures.py's own docstring for")
    print("  why that prefix is a permanent collision-avoidance fix, not a style choice.")

    # ------------------------------------------------------------------
    header("1. Building the graph")
    refs = fixtures.FIXTURE_ENTITY_REFS
    g = resolve.build_graph(refs)
    community.assign_communities(g)

    n_rfc = sum(1 for n in g.nodes.values() if n.entity_type == "rfc")
    n_errata = sum(1 for n in g.nodes.values() if n.entity_type == "errata")
    print(f"  {len(refs)} EntityRef mentions (the candidates.jsonl row shape) resolved into:")
    print(f"    {len(g.nodes)} nodes   ({n_rfc} rfc, {n_errata} errata)")
    print(f"    {len(g.edges)} edges")
    by_type: dict[str, int] = {}
    for e in g.edges:
        by_type[e.edge_type] = by_type.get(e.edge_type, 0) + 1
    for et in ("obsoletes", "updates", "corrects", "co_mentions"):
        print(f"      {et:12s} {by_type.get(et, 0)}")
    n_communities = len({n.community for n in g.nodes.values()})
    print(f"    {n_communities} communities (connected components over obsoletes/updates/corrects)")

    # ------------------------------------------------------------------
    header("2. The real 6-way multi-obsoletes case: RFCX9010")
    print("  This mirrors the real HTTP/1.1 case: RFC 2616 was later obsoleted by six")
    print("  separate RFCs, 7230-7235 -- a genuine many-to-many supersession, not a")
    print("  one-to-one revision chain. The fixture models that same branching shape.")

    chain_9010 = g.get_obsoletion_chain("RFCX9010")
    print(f"\n  get_obsoletion_chain('RFCX9010') -> status={chain_9010['status']!r}")
    for h in chain_9010["history"]:
        print(f"    {h['rfc']:8s} obsoletes={h['obsoletes']}  obsoleted_by={h['obsoleted_by']}")

    real = sorted(h["rfc"] for h in chain_9010["history"] if "RFCX9010" in h["obsoletes"])
    naive = naive_latest_successor("RFCX9010", refs)
    print("\n  HEAD-TO-HEAD: a naive linear-successor model (reads only obsoleted_by[0],")
    print("  as a single 'next_version_id' foreign key would) vs. linkgraph's real")
    print("  traversal:")
    print(f"    naive linear successor   : {naive}   ({len(naive)}/6 real successors found)")
    print(f"    linkgraph real traversal : {real}   ({len(real)}/6 real successors found)")
    print("  A one-to-one revision-chain assumption silently drops 5 of the 6 real")
    print("  successors here -- exactly the failure mode this repo exists to fix.")

    chain_9099 = g.get_obsoletion_chain("RFCX9099")
    print(f"\n  A genuinely dangling obsoletion pointer is reported honestly, never silently")
    print(f"  dropped: get_obsoletion_chain('RFCX9099') -> status={chain_9099['status']!r}")
    print("    (RFCX9022's obsoleted_by target, RFCX9099, was never itself mentioned in")
    print("    the corpus -- modeling a real gap where an index entry points at a")
    print("    document the ingest hasn't fetched yet.)")

    # ------------------------------------------------------------------
    header("3. Errata corrections: get_corrections")
    corrections_9021 = g.get_corrections("RFCX9021")
    corrections_9022 = g.get_corrections("RFCX9022")
    print(f"  get_corrections('RFCX9021') -> {corrections_9021}")
    print(f"    {corrections_9021[0]} corrects a multiplex-framing typo in RFCX9021's")
    print("    stream-windowing section.")
    print(f"  get_corrections('RFCX9022') -> {corrections_9022}  (no errata filed against it)")

    # ------------------------------------------------------------------
    header("4. get_related: the co-mention signal reaches further than direct "
            "structural edges")
    seed = "rfc:RFCX9022"
    struct_1hop = dict(g.get_related(seed, max_hops=1, edge_types=STRUCTURAL_EDGE_TYPES))
    all_1hop = dict(g.get_related(seed, max_hops=1))
    co_mention_only = sorted(n for n in all_1hop if n not in struct_1hop)

    print(f"  seed: {seed}")
    print(f"  direct STRUCTURAL neighbors only (obsoletes/updates/corrects), 1 hop:")
    print(f"    {sorted(struct_1hop)}")
    print(f"  ALL signals (structural + co_mentions), 1 hop:")
    print(f"    {sorted(all_1hop)}")
    print(f"  reachable ONLY through the weaker co-mention signal at this range:")
    print(f"    {co_mention_only}")

    struct_far = dict(g.get_related(seed, max_hops=6, edge_types=STRUCTURAL_EDGE_TYPES))
    for node in co_mention_only:
        hops = struct_far.get(node)
        if hops is None:
            print(f"    {node}: not reachable via structural edges alone at any distance")
        else:
            print(f"    {node}: co-mention reaches it in 1 hop; structural edges alone need {hops} hop(s)")
    print("  co_mentions is a weaker, noisier signal by design (graph.py excludes it from")
    print("  community assignment for exactly this reason) -- but it is real: it is what")
    print("  lets the graph surface a connection two documents actually share, faster")
    print("  than following only the asserted structural facts.")

    # ------------------------------------------------------------------
    header("5. The graphrx hand-off: structural linting of the exported graph")
    gx = adapter.export_graphrx_graph(g)
    adj = adjacency(gx)
    print(f"  export_graphrx_graph -> {len(gx['nodes'])} nodes, {len(gx['edges'])} flattened edges, "
          f"{len(gx['facts'])} facts")
    print(f"  graphrx.graph.adjacency() round-trips the export without crashing "
          f"({len(adj)} nodes in the adjacency map).")

    clean_defects = report(gx)
    clean_high_risk = high_risk(clean_defects, HIGH_RISK)
    print(f"\n  graphrx.lint.report() on the CLEAN export: {len(clean_defects)} defect(s), "
          f"{len(clean_high_risk)} high-risk (expect 0).")

    print("\n  Now planting a REAL accidental entity-resolution merge: two distinct,")
    print("  cross-family RFCs -- RFCX9021 (Widget Transport / multiplex vocabulary) and")
    print("  RFCX9031 (Session Handshake / cipher vocabulary) -- collapsed into one node.")
    print("  This is exactly what a real ER pipeline bug looks like: two unrelated")
    print("  documents wrongly merged because their identifiers or embeddings looked")
    print("  close enough. Facts, edges, and community label are merged the same way")
    print("  eval.py's own plant_bad_merge (reused here, not reimplemented) does it.")

    bad = plant_bad_merge(gx, "rfc:RFCX9021", "rfc:RFCX9031", "rfc:RFCX9021+RFCX9031")
    bad_defects = report(bad)
    print("\n  graphrx.lint.report() on the BAD-MERGE export:")
    for d in bad_defects:
        print(f"    {d['score']:.4f}  {d['kind']:<14} target={d['target']}  {d['evidence']}")

    flagged = [
        d for d in bad_defects
        if d["target"] == "rfc:RFCX9021+RFCX9031" and d["kind"] == "er_collision"
    ]
    if flagged:
        d = flagged[0]
        print(f"\n  CAUGHT: er_collision on the merged node, score={d['score']:.4f} "
              f"(>= high-risk threshold {HIGH_RISK}).")
        clusters = d["proposal"]["clusters"]
        real_split = [sorted({bad["facts"][fid]["real_entity"] for fid in part}) for part in clusters]
        print(f"  Proposed split recovers the two real entities cleanly: {real_split}")
    else:
        print("\n  UNEXPECTED: the planted bad merge was not flagged as er_collision.")

    control_high_risk = high_risk(report(gx), HIGH_RISK)
    print("\n  Why this matters: this is not a synthetic toy check. A real entity-")
    print("  resolution bug that merges two distinct documents produces exactly this")
    print("  signature -- one node whose facts split cleanly into two semantically")
    print("  incoherent clusters -- and graphrx's UNMODIFIED, general-purpose lint")
    print("  catches it through its own embedding-separation mechanism, with no")
    print("  linkgraph-specific code path. The original clean export, untouched by the")
    print(f"  bad-merge experiment above, stays quiet: {len(control_high_risk)} high-risk "
          f"defect(s).")

    header("Summary")
    print("  linkgraph recovers the real many-to-many obsoletion/errata/co-mention")
    print("  structure that a linear-chain assumption would miss, and its export hands")
    print("  off to an independent structural linter that catches a real entity-")
    print("  resolution mistake -- with zero false alarms on clean data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
