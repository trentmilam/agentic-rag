"""LinkGraph RED/GREEN self-test -- proves the graph genuinely recovers the
REAL many-to-many obsoletion structure (not a linear-chain approximation) and
that the ``graphrx`` hand-off catches a genuinely planted bad merge.

    python eval.py

Deterministic: the fixture is fully hand-authored (no RNG, no wall-clock).

GREEN : on the fixture's clean export, ``graphrx.lint.report()`` finds ZERO
        high-risk defects; ``get_obsoletion_chain``/``get_corrections``/
        ``get_related`` recover the real branching structure, including a
        genuinely dangling obsoletion pointer.
RED   : a deliberately planted bad ER merge (two real, cross-family nodes
        collapsed into one -- the same technique graphrx/fixtures.py itself
        uses to plant its own collision) is caught by the UNMODIFIED
        ``graphrx.lint.report()`` via its real embedding-separation mechanism.
HEAD-TO-HEAD : a naive "linear successor" incumbent (read only the first
        ``obsoleted_by`` entry, as a one-to-one revision-chain model would)
        is compared against LinkGraph's real traversal on the fixture's
        6-way multi-obsoletes case -- the exact scenario this repo exists to
        handle correctly.
"""
import copy
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from linkgraph._paths import add_sibling_paths  # noqa: E402

add_sibling_paths()

from linkgraph import adapter, community, fixtures, resolve  # noqa: E402
from linkgraph.contract import EntityRef  # noqa: E402

from graphrx.graph import adjacency  # noqa: E402
from graphrx.lint import high_risk, report  # noqa: E402

HIGH_RISK = 0.25


def naive_latest_successor(rfc_id: str, refs: list[EntityRef]) -> list[str]:
    """Incumbent baseline: what a linear-revision-chain assumption recovers.

    Many document-revision trackers (and the earlier, now-abandoned synthetic
    -corpus design this very repo would have needed) model supersession as a
    simple one-to-one chain: each document has AT MOST one successor. Applied
    here, that means reading only ``extra["obsoleted_by"][0]`` -- the first
    successor listed -- and discarding the rest. This is a fair, realistic
    incumbent (not a strawman): it is exactly what a single "next_version_id"
    foreign key would capture, and it is exactly what breaks on RFC 2616's
    real six-way obsoletion.
    """
    for ref in refs:
        if ref.entity_type == "rfc" and ref.entity_id == rfc_id:
            successors = ref.extra.get("obsoleted_by") or []
            return [str(successors[0])] if successors else []
    return []


def plant_bad_merge(gx_graph: dict, node_a: str, node_b: str, merged_id: str) -> dict:
    """Mutate a COPY of a clean graphrx export by merging two real, distinct
    linkgraph nodes into one -- the same technique ``graphrx/fixtures.py``
    uses in ``build_flawed_graph`` to plant its own ER-collision defect:
    concatenate both nodes' facts, redirect every edge touching either
    original endpoint to the merged id, drop the two originals, keep one
    node's community label.
    """
    g = copy.deepcopy(gx_graph)
    facts_a = g["nodes"][node_a]["facts"]
    facts_b = g["nodes"][node_b]["facts"]
    community_label = g["nodes"][node_a]["community"]
    g["nodes"][merged_id] = {"facts": facts_a + facts_b, "community": community_label}
    del g["nodes"][node_a]
    del g["nodes"][node_b]
    new_edges = []
    for u, v in g["edges"]:
        u2 = merged_id if u in (node_a, node_b) else u
        v2 = merged_id if v in (node_a, node_b) else v
        if u2 == v2:
            continue
        new_edges.append(tuple(sorted((u2, v2))))
    g["edges"] = sorted(set(new_edges))
    return g


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def main() -> int:
    checks = {}
    refs = fixtures.FIXTURE_ENTITY_REFS
    g = resolve.build_graph(refs)
    community.assign_communities(g)
    gx = adapter.export_graphrx_graph(g)

    # ---------- sanity: adjacency() round-trips the flattened export --------
    adj = adjacency(gx)
    checks["adjacency_roundtrip_no_crash"] = isinstance(adj, dict) and len(adj) == len(gx["nodes"])
    checks["adjacency_reflects_obsoletes_edge"] = "rfc:RFCX9010" in adj["rfc:RFCX9021"]

    # ---------- GREEN: clean export is quiet ----------
    clean_defects = report(gx)
    checks["green_clean_no_high_risk"] = len(high_risk(clean_defects, HIGH_RISK)) == 0

    # ---------- GREEN: real branching obsoletion structure ----------
    chain_9010 = g.get_obsoletion_chain("RFCX9010")
    successors_9010 = sorted(h["rfc"] for h in chain_9010["history"] if "RFCX9010" in h["obsoletes"])
    checks["green_9010_status_obsoleted"] = chain_9010["status"] == "obsoleted"
    checks["green_9010_six_real_successors"] = successors_9010 == \
        ["RFCX9021", "RFCX9022", "RFCX9023", "RFCX9024", "RFCX9025", "RFCX9026"]

    chain_9030 = g.get_obsoletion_chain("RFCX9030")
    checks["green_9030_two_successors"] = sorted(
        h["rfc"] for h in chain_9030["history"] if "RFCX9030" in h["obsoletes"]
    ) == ["RFCX9031", "RFCX9032"]

    checks["green_9021_status_current"] = g.get_obsoletion_chain("RFCX9021")["status"] == "current"

    # ---------- GREEN: a genuinely dangling pointer, correctly reported ----
    chain_9099 = g.get_obsoletion_chain("RFCX9099")
    checks["green_9099_dangling"] = chain_9099["status"] == "dangling"
    checks["green_9099_still_in_real_history"] = any(
        h["rfc"] == "RFCX9099" for h in chain_9099["history"]
    )

    # ---------- GREEN: corrections + related lookups ----------
    checks["green_corrections_9021"] = g.get_corrections("RFCX9021") == ["ERRX100"]
    checks["green_corrections_9022_empty"] = g.get_corrections("RFCX9022") == []
    related_1hop = {n for n, _ in g.get_related("rfc:RFCX9022", max_hops=1)}
    related_2hop = {n for n, _ in g.get_related("rfc:RFCX9022", max_hops=2)}
    checks["green_related_1hop_direct_only"] = "rfc:RFCX9024" not in related_1hop
    checks["green_related_2hop_reaches_sibling"] = "rfc:RFCX9024" in related_2hop

    # ---------- RED: a deliberately planted bad ER merge is caught ----------
    bad = plant_bad_merge(gx, "rfc:RFCX9021", "rfc:RFCX9031", "rfc:RFCX9021+RFCX9031")
    bad_defects = report(bad)
    by_kind = {d["kind"]: d for d in bad_defects if d["target"] == "rfc:RFCX9021+RFCX9031"}
    checks["red_bad_merge_flagged"] = "er_collision" in by_kind
    checks["red_bad_merge_high_risk"] = (
        "er_collision" in by_kind and by_kind["er_collision"]["score"] >= HIGH_RISK
    )
    checks["red_bad_merge_split_is_pure"] = False
    if "er_collision" in by_kind:
        clusters = by_kind["er_collision"]["proposal"]["clusters"]
        real_entities = [
            {bad["facts"][fid]["real_entity"] for fid in part} for part in clusters
        ]
        checks["red_bad_merge_split_is_pure"] = all(len(s) == 1 for s in real_entities)

    # ---------- NEGATIVE CONTROL: the merge-free clean graph stays quiet ----
    checks["control_clean_still_quiet_after_bad_merge_check"] = len(high_risk(report(gx), HIGH_RISK)) == 0

    # ---------- HEAD-TO-HEAD: naive linear successor vs real traversal -----
    naive = naive_latest_successor("RFCX9010", refs)
    real = successors_9010
    checks["ab_naive_finds_only_one"] = len(naive) == 1
    checks["ab_real_finds_all_six"] = len(real) == 6
    checks["ab_real_strictly_more_than_naive"] = len(real) > len(naive)

    # ---------- determinism ----------
    shuffled_refs = list(reversed(refs))
    g2 = resolve.build_graph(shuffled_refs)
    community.assign_communities(g2)
    checks["determinism_edges"] = (
        sorted((e.src, e.dst, e.edge_type) for e in g.edges)
        == sorted((e.src, e.dst, e.edge_type) for e in g2.edges)
    )
    checks["determinism_chain"] = g.get_obsoletion_chain("RFCX9010") == g2.get_obsoletion_chain("RFCX9010")

    # ---------------------------- report ----------------------------
    print(f"[fixture] {len(refs)} EntityRef mentions -> {len(g.nodes)} nodes, {len(g.edges)} edges")
    print("\n=== graphrx hand-off: lint report on the CLEAN export ===")
    print(f"  defects: {clean_defects}  (high-risk: {high_risk(clean_defects, HIGH_RISK)})")
    print("\n=== graphrx hand-off: lint report on the BAD-MERGE export ===")
    for d in bad_defects:
        print(f"  {d['score']:.4f}  {d['kind']:<14} target={d['target']}  {d['evidence']}")
    print("\n=== real obsoletion chain: RFCX9010 (6-way multi-obsoletes, HTTP/2616-shaped) ===")
    for h in chain_9010["history"]:
        print(f"  {h['rfc']:6s} obsoletes={h['obsoletes']}  obsoleted_by={h['obsoleted_by']}")
    print(f"  status(RFCX9010)={chain_9010['status']}  status(RFCX9099, dangling pointer)={chain_9099['status']}")
    print("\n=== HEAD-TO-HEAD: naive linear-successor incumbent vs real traversal ===")
    print(f"  naive (reads obsoleted_by[0] only) : {naive}  ({len(naive)}/6 real successors found)")
    print(f"  LinkGraph get_obsoletion_chain      : {real}  ({len(real)}/6 real successors found)")
    print("\n=== checks ===")
    for k, v in checks.items():
        print(f"{'OK  ' if v else 'FAIL'} {k}")
    passed = all(checks.values())
    print("\nRESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
