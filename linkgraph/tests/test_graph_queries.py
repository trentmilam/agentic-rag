"""LinkGraph.get_related / get_obsoletion_chain / get_corrections against the
real branching + dangling structure in the fixture."""


def test_get_related_respects_max_hops(graph):
    one_hop = {n for n, _ in graph.get_related("rfc:RFCX9022", max_hops=1)}
    two_hop = {n for n, _ in graph.get_related("rfc:RFCX9022", max_hops=2)}
    # rfc:RFCX9024 only shares RFCX9010 as a common obsoletes-target with RFCX9022 -- two
    # hops away, never one.
    assert "rfc:RFCX9024" not in one_hop
    assert "rfc:RFCX9024" in two_hop


def test_get_related_hop_distance_is_reported(graph):
    related = dict(graph.get_related("rfc:RFCX9022", max_hops=2))
    assert related["rfc:RFCX9010"] == 1
    assert related["rfc:RFCX9024"] == 2


def test_get_related_edge_types_filter(graph):
    obsoletes_only = {n for n, _ in graph.get_related("rfc:RFCX9022", max_hops=1, edge_types={"obsoletes"})}
    co_mentions_only = {n for n, _ in graph.get_related("rfc:RFCX9022", max_hops=1, edge_types={"co_mentions"})}
    assert obsoletes_only == {"rfc:RFCX9010", "rfc:RFCX9099"}
    assert co_mentions_only == {"rfc:RFCX9021", "rfc:RFCX9023", "errata:ERRX100"}


def test_get_related_min_score_does_not_filter_structural_edges(graph):
    # obsoletes/updates/corrects are asserted facts, never scored -- an
    # arbitrarily high min_score must not drop them.
    related = {n for n, _ in graph.get_related("rfc:RFCX9022", max_hops=1, min_score=1000.0)}
    assert {"rfc:RFCX9010", "rfc:RFCX9099"} <= related


def test_get_related_min_score_filters_co_mentions(graph):
    below = {n for n, _ in graph.get_related("rfc:RFCX9022", max_hops=1, min_score=0.0)}
    above = {n for n, _ in graph.get_related("rfc:RFCX9022", max_hops=1, min_score=1000.0)}
    assert "rfc:RFCX9021" in below  # a real co-mention neighbor at score 1.0
    assert "rfc:RFCX9021" not in above  # filtered out once min_score exceeds it


def test_get_related_excludes_the_seed_itself(graph):
    related = {n for n, _ in graph.get_related("rfc:RFCX9022", max_hops=5)}
    assert "rfc:RFCX9022" not in related


def test_get_related_unknown_entity_returns_empty(graph):
    assert graph.get_related("rfc:does-not-exist") == []


def test_obsoletion_chain_branches_for_a_real_multi_obsoletes_rfc(graph):
    chain = graph.get_obsoletion_chain("RFCX9010")
    direct_successors = sorted(h["rfc"] for h in chain["history"] if "RFCX9010" in h["obsoletes"])
    assert direct_successors == ["RFCX9021", "RFCX9022", "RFCX9023", "RFCX9024", "RFCX9025", "RFCX9026"]
    assert chain["status"] == "obsoleted"


def test_obsoletion_chain_second_branch_point(graph):
    # RFCX9022 is itself obsoleted by RFCX9099 -- a SECOND branch nested inside RFCX9010's
    # component, proving history isn't flattened to one level.
    chain = graph.get_obsoletion_chain("RFCX9010")
    node_9022 = next(h for h in chain["history"] if h["rfc"] == "RFCX9022")
    assert node_9022["obsoleted_by"] == ["RFCX9099"]


def test_obsoletion_chain_current_status_for_an_unobsoleted_leaf(graph):
    assert graph.get_obsoletion_chain("RFCX9026")["status"] == "current"


def test_obsoletion_chain_dangling_status_for_a_never_seen_pointer(graph):
    chain = graph.get_obsoletion_chain("RFCX9099")
    assert chain["status"] == "dangling"
    # still graph-connected: the dangling node's OWN edge is real and present
    assert any(h["rfc"] == "RFCX9099" and h["obsoletes"] == ["RFCX9022"] for h in chain["history"])


def test_obsoletion_chain_updates_edges_are_excluded():
    # rfc:RFCX9040 UPDATES (not obsoletes) RFCX9010 -- it must not appear in RFCX9010's
    # obsoletion history at all.
    import linkgraph.resolve as resolve
    import linkgraph.fixtures as fixtures
    g = resolve.build_graph(fixtures.FIXTURE_ENTITY_REFS)
    chain = g.get_obsoletion_chain("RFCX9010")
    assert not any(h["rfc"] == "RFCX9040" for h in chain["history"])


def test_get_corrections_returns_bare_errata_ids(graph):
    assert graph.get_corrections("RFCX9021") == ["ERRX100"]
    assert graph.get_corrections("RFCX9031") == ["ERRX101"]


def test_get_corrections_empty_when_no_errata_corrects_it(graph):
    assert graph.get_corrections("RFCX9022") == []
