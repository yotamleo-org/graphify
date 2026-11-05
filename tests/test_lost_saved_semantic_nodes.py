"""_lost_saved_semantic_nodes: a semantic ghost deduplicated into its AST twin
(#1145 extended) is preserved, not lost."""
from __future__ import annotations

import json
from pathlib import Path

from graphify.build import _lost_saved_semantic_nodes, build_from_json
from graphify.export import to_json
from graphify.watch import _check_shrink


def _sem(node_id: str, label: str, sf: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "file_type": "code",
        "source_file": sf,
        "source_location": None,
        "_origin": "semantic",
    }


def _ast(node_id: str, label: str, sf: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "file_type": "code",
        "source_file": sf,
        "source_location": "L10",
        "_origin": "ast",
    }


def test_same_id_present_is_not_lost():
    saved = [_sem("foo_bar", "bar", "src/foo.py")]
    new = [_sem("foo_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, new) == []


def test_deduplicated_into_ast_node_is_not_lost():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [_ast("foo_py_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, new) == []


def test_non_ast_replacement_is_not_excused():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [_sem("other_bar", "bar", "src/foo.py")]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_ast_label_collision_is_not_excused():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [
        _ast("foo_py_bar_1", "bar", "src/foo.py"),
        _ast("foo_py_bar_2", "bar", "src/foo.py"),
    ]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_ast_collision_after_normalization_is_not_excused():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [
        _ast("foo_py_bar_1", "bar", "src/foo.py"),
        _ast("foo_py_bar_2", "bar", "src\\foo.py"),
    ]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_dedup_match_normalizes_source_file():
    saved = [_sem("ghost_bar", "bar", "src\\foo.py")]
    new = [_ast("foo_py_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, new) == []


def test_genuinely_lost_node_is_reported():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [
        _ast("foo_py_baz", "baz", "src/foo.py"),
        _ast("other_py_bar", "bar", "src/other.py"),
    ]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_node_in_deleted_source_is_not_lost():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, [], {"src/foo.py"}) == []


def test_node_in_other_file_not_excused_by_deleted_source():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    lost = _lost_saved_semantic_nodes(saved, [], {"src/other.py"})
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_malformed_non_string_source_file_does_not_crash():
    # Truthy non-string source_file in new_nodes or saved_nodes must not raise AttributeError
    saved = [{"id": "s1", "label": "S1", "source_file": 123, "_origin": "semantic"}]
    new = [{"id": "n1", "label": "N1", "source_file": True}]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["s1"]


# --- end-to-end: the write paths that call the guard (#4389) ---


def _saved_graph(tmp_path: Path, sem: dict) -> tuple[Path, dict]:
    out = tmp_path / "graph.json"
    assert to_json(build_from_json({"nodes": [sem], "edges": []}), {}, str(out), force=True)
    return out, json.loads(out.read_text(encoding="utf-8"))


def _node_data(G) -> dict:
    return {"nodes": [{"id": nid, **attrs} for nid, attrs in G.nodes(data=True)], "links": []}


def test_to_json_writes_after_ghost_dedup(tmp_path):
    sem = _sem("src_models_user_ts_user", "User", "src/models/user.ts")
    out, _ = _saved_graph(tmp_path, sem)
    G = build_from_json({"nodes": [sem, _ast("user_user", "User", "src/models/user.ts")], "edges": []})
    assert list(G.nodes) == ["user_user"]  # ghost id folded into its AST twin
    assert to_json(G, {}, str(out)) is True


def test_to_json_still_refuses_genuine_loss(tmp_path, capsys):
    sem = _sem("src_models_user_ts_user", "User", "src/models/user.ts")
    out, _ = _saved_graph(tmp_path, sem)
    G = build_from_json({"nodes": [_ast("user_account", "Account", "src/models/user.ts")], "edges": []})
    assert to_json(G, {}, str(out)) is False
    assert "src_models_user_ts_user" in capsys.readouterr().err


def test_check_shrink_allows_ghost_dedup(tmp_path):
    sem = _sem("src_models_user_ts_user", "User", "src/models/user.ts")
    _, existing = _saved_graph(tmp_path, sem)
    G = build_from_json({"nodes": [sem, _ast("user_user", "User", "src/models/user.ts")], "edges": []})
    assert _check_shrink(force=False, existing_data=existing, new_data=_node_data(G)) is True


# --- label-only file twin: build_from_json Pass 2b (#3344) folds a document's
# mention of a file into that file's AST node (#4389 cluster-only follow-up) ---


def _mention(node_id: str, label: str, doc: str) -> dict:
    return {"id": node_id, "label": label, "file_type": "code", "source_file": doc, "_origin": "semantic"}


def _ast_file(node_id: str, sf: str) -> dict:
    return {
        "id": node_id,
        "label": sf.rsplit("/", 1)[-1],
        "file_type": "code",
        "source_file": sf,
        "source_location": "L1",
        "_origin": "ast",
    }


def test_file_mention_folded_into_ast_file_node_is_not_lost():
    saved = [_mention("readme_config", "src/config.php", "README.md")]
    new = [_ast_file("src_config", "src/config.php")]
    folded: dict[str, str] = {}
    assert _lost_saved_semantic_nodes(saved, new, None, folded) == []
    assert folded == {"readme_config": "src_config"}


def test_rich_semantic_file_mention_is_not_exempt_from_shrink_guard():
    """#4896: the builder preserves rich cross-file semantics, so the
    shrink guard must not pretend that a missing one was folded away.
    """
    rich = {**_mention("semantic_doc", "config.php", "notes/plan.md"),
            "rationale": "Unique source-specific analysis"}
    ast = _ast_file("src_config", "src/config.php")
    assert [n["id"] for n in _lost_saved_semantic_nodes([rich], [ast])] == [
        "semantic_doc"
    ]
    payload = {"nodes": [rich, ast], "edges": [], "hyperedges": []}
    graph = build_from_json(payload)
    assert {"semantic_doc", "src_config"} <= set(graph.nodes)
    folded = {}
    assert _lost_saved_semantic_nodes([rich], [
        {**dict(graph.nodes[nid]), "id": nid} for nid in graph.nodes
    ], folded=folded) == []
    assert folded == {}


def test_rich_semantics_survive_repeated_build_and_serialization(tmp_path):
    """#4896: the source-specific rationales must survive cold reloading."""
    rich_a = {**_mention("sem_a", "config.php", "docs/a.md"),
              "rationale": "First source's unique explanation"}
    rich_b = {**_mention("sem_b", "config.php", "docs/b.yaml"),
              "rationale": "Second source's separate explanation"}
    bare = _mention("bare_mention", "config.php", "README.md")
    ast = _ast_file("src_config", "src/config.php")
    graph = build_from_json({"nodes": [ast, rich_a, rich_b, bare], "edges": []})
    output = tmp_path / "graph.json"
    for _ in range(2):
        assert {"src_config", "sem_a", "sem_b"} <= set(graph.nodes)
        assert "bare_mention" not in graph.nodes
        assert graph.nodes["sem_a"]["rationale"] == rich_a["rationale"]
        assert graph.nodes["sem_b"]["rationale"] == rich_b["rationale"]
        assert to_json(graph, {}, str(output))
        graph = build_from_json(json.loads(output.read_text(encoding="utf-8")))


def test_file_mention_matching_two_ast_files_is_still_lost():
    # Pass 2b leaves an ambiguous label unmerged, so its absence is a real loss.
    saved = [_mention("readme_index", "index.ts", "README.md")]
    new = [_ast_file("a_index", "a/index.ts"), _ast_file("b_index", "b/index.ts")]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["readme_index"]


def _mixed_saved_graph(tmp_path: Path) -> Path:
    # A saved graph that still holds the mention beside its AST file node,
    # as reported on #4389 for graphifyy 0.9.95.
    out = tmp_path / "graph.json"
    out.write_text(json.dumps({
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            _ast_file("src_config", "src/config.php"),
            _mention("readme_config", "src/config.php", "README.md"),
            {"id": "readme", "label": "README.md", "file_type": "document",
             "source_file": "README.md", "_origin": "semantic"},
        ],
        "links": [{"source": "readme", "target": "readme_config", "relation": "describes",
                   "confidence": "EXTRACTED", "source_file": "README.md"}],
    }), encoding="utf-8")
    return out


def test_to_json_writes_recluster_that_folds_file_mention(tmp_path):
    out = _mixed_saved_graph(tmp_path)
    G = build_from_json(json.loads(out.read_text(encoding="utf-8")))
    assert sorted(G.nodes) == ["readme", "src_config"]
    assert G.has_edge("readme", "src_config")  # the edge follows the fold
    assert to_json(G, {}, str(out)) is True


def test_to_json_new_twin_does_not_offset_another_loss(tmp_path, capsys):
    # The twin is new in this run, so the fold is not a saved duplicate going
    # away: losing src_other must still refuse the write.
    out = tmp_path / "graph.json"
    out.write_text(json.dumps({"nodes": [
        _mention("readme_config", "src/config.php", "README.md"),
        _ast_file("src_other", "src/other.php"),
    ], "links": []}), encoding="utf-8")
    G = build_from_json({"nodes": [_ast_file("src_config", "src/config.php")], "edges": []})
    assert to_json(G, {}, str(out)) is False
    assert "new graph has 1 nodes" in capsys.readouterr().err


def test_same_source_yaml_semantic_evidence_survives_new_ast_full_build(tmp_path):
    """#4896: updating a formerly semantic-only YAML must retain source-specific
    rationale even when that exact YAML becomes AST-extractable in newer Graphify.
    """
    rich = {**_mention("legacy_yaml_id", "automation.yaml", "config/automation.yaml"),
            "file_type": "document", "rationale": "Reviewed migration contract"}
    ast = _ast_file("canonical_yaml_ast", "config/automation.yaml")
    related = {"id": "docs_review", "label": "Review", "file_type": "concept",
               "source_file": "docs/review.md", "_origin": "semantic"}
    payload = {"nodes": [ast, rich, related],
               "edges": [{"source": "docs_review", "target": "legacy_yaml_id",
                          "relation": "references", "confidence": "EXTRACTED",
                          "source_file": "docs/review.md"}]}
    g = build_from_json(payload)
    assert "canonical_yaml_ast" in g and "legacy_yaml_id" in g
    assert g.nodes["legacy_yaml_id"]["rationale"] == rich["rationale"]
    assert g.has_edge("docs_review", "legacy_yaml_id")
    out = tmp_path / "graph.json"
    assert to_json(g, {}, str(out)) is True
    reloaded = build_from_json(json.loads(out.read_text()))
    assert "legacy_yaml_id" in reloaded
    assert reloaded.nodes["legacy_yaml_id"]["rationale"] == rich["rationale"]
    assert _lost_saved_semantic_nodes([rich], [
        {"id": n, **dict(reloaded.nodes[n])} for n in reloaded.nodes
    ]) == []
    # An AST-only candidate may NOT claim this independently evidenced
    # semantic node has been safely folded.
    assert [n["id"] for n in _lost_saved_semantic_nodes([rich], [ast])] == [
        "legacy_yaml_id"
    ]


def test_disambiguated_yaml_ast_file_excuses_only_matching_bare_mention():
    """Full corpus may path-qualify the AST file label after a same-source
    bare YAML mention was legitimately folded into the real file node.
    """
    saved = [_mention("legacy_case", "case-a.yaml", "cases/a/case-a.yaml")]
    ast_one = {**_ast_file("case_a_ast", "cases/a/case-a.yaml"),
               "label": "a/case-a.yaml"}
    ast_other = {**_ast_file("other_ast", "cases/b/case-a.yaml"),
                 "label": "b/case-a.yaml"}
    folded = {}
    assert _lost_saved_semantic_nodes(saved, [ast_one, ast_other], folded=folded) == []
    assert folded == {"legacy_case": "case_a_ast"}
    assert [n["id"] for n in _lost_saved_semantic_nodes(saved, [ast_other])] == [
        "legacy_case"
    ]


def test_evidence_free_same_source_file_mention_still_folds():
    saved = [_mention("plain_yaml_mention", "config.yaml", "config/config.yaml")]
    ast = _ast_file("config_ast", "config/config.yaml")
    g = build_from_json({"nodes": [ast, *saved], "edges": []})
    assert "config_ast" in g and "plain_yaml_mention" not in g
    assert _lost_saved_semantic_nodes(saved, [
        {"id": n, **dict(g.nodes[n])} for n in g.nodes
    ]) == []


def test_metadata_only_mention_is_not_independent_evidence():
    """#4896: `metadata` and `captured_at` ride along on ordinary INFERRED
    mention ghosts, so they must not count as independent provenance. A ghost
    carrying only those still folds into its AST file-self twin instead of
    surviving as a duplicate."""
    meta_only = {**_mention("meta_ghost", "config.yaml", "config/config.yaml"),
                 "metadata": {"confidence": "INFERRED"}, "captured_at": "2026-11-02"}
    saved = [meta_only]
    ast = _ast_file("config_ast", "config/config.yaml")
    g = build_from_json({"nodes": [ast, *saved], "edges": []})
    assert "config_ast" in g and "meta_ghost" not in g
    folded: dict[str, str] = {}
    assert _lost_saved_semantic_nodes(saved, [
        {"id": n, **dict(g.nodes[n])} for n in g.nodes
    ], folded=folded) == []
    assert folded == {"meta_ghost": "config_ast"}
# --- a saved semantic node folded into a same-file, same-label semantic twin (HIMMEL-9232) ---


def _saved_twin_graph(tmp_path: Path) -> Path:
    # A note that lists renamed ids makes the extractor emit an old path id next
    # to its file-scoped twin: both saved, one node after the reload.
    out = tmp_path / "graph.json"
    out.write_text(json.dumps({"nodes": [
        _sem("scripts_tick", "tick.sh", "docs/renamed.md"),
        {**_sem("docs_renamed_md_tick_sh", "tick.sh", "docs/renamed.md"), "source_location": "N17"},
        _sem("docs_renamed_md_other", "other", "docs/renamed.md"),
    ], "links": []}), encoding="utf-8")
    return out


def test_same_file_semantic_fold_is_not_lost():
    twin = {**_sem("new_tick", "tick.sh", "docs/notes.md"), "source_location": "N1"}
    saved = [_sem("old_tick", "tick.sh", "docs/notes.md"), twin]
    folded: dict[str, str] = {}
    assert _lost_saved_semantic_nodes(saved, [twin], None, folded, semantic_fold=True) == []
    assert folded == {"old_tick": "new_tick"}


def _located(node_id: str, loc: str = "N1", label: str = "tick.sh") -> dict:
    return {**_sem(node_id, label, "docs/notes.md"), "source_location": loc}


def test_same_file_semantic_fold_needs_a_located_twin():
    # Pass 1 makes only a located semantic node canonical: with no location on
    # either saved node, nothing folded and the missing one is a real loss.
    a, b = _sem("a_tick", "tick.sh", "docs/notes.md"), _sem("b_tick", "tick.sh", "docs/notes.md")
    lost = _lost_saved_semantic_nodes([a, b], [a], semantic_fold=True)
    assert [n["id"] for n in lost] == ["b_tick"]


def test_same_file_semantic_fold_follows_sort_order():
    # The canonical is the first located id in sorted order, so a_tick survives
    # the fold and b_tick is the ghost. Losing the canonical is a real loss.
    a, b = _located("a_tick", "N1"), _located("b_tick", "N2")
    assert _lost_saved_semantic_nodes([a, b], [a], semantic_fold=True) == []
    lost = _lost_saved_semantic_nodes([a, b], [b], semantic_fold=True)
    assert [n["id"] for n in lost] == ["a_tick"]


def test_same_file_semantic_fold_skips_a_key_with_two_ast_nodes():
    # Pass 2 leaves a key shared by 2+ AST nodes alone, so nothing folded there.
    ast_1, ast_2 = _ast("ast_1", "tick.sh", "docs/notes.md"), _ast("ast_2", "tick.sh", "docs/notes.md")
    twin, ghost = _located("y_tick"), _sem("z_tick", "tick.sh", "docs/notes.md")
    lost = _lost_saved_semantic_nodes([ast_1, ast_2, twin, ghost], [ast_1, ast_2, twin], semantic_fold=True)
    assert [n["id"] for n in lost] == ["z_tick"]


def test_same_file_semantic_fold_removes_one_ghost_per_key():
    # Pass 2 keeps one ghost per key: with a_tick canonical, only c_tick (the last
    # in sorted order) goes. b_tick missing as well is a second, real loss.
    a, b, c = _located("a_tick"), _sem("b_tick", "tick.sh", "docs/notes.md"), _sem("c_tick", "tick.sh", "docs/notes.md")
    assert _lost_saved_semantic_nodes([a, b, c], [a, b], semantic_fold=True) == []
    lost = _lost_saved_semantic_nodes([a, b, c], [a], semantic_fold=True)
    assert [n["id"] for n in lost] == ["b_tick"]


def test_same_file_semantic_fold_never_excuses_the_raw_path():
    # watch._check_shrink (--no-cluster) never calls build_from_json, so nothing folds.
    twin = _located("new_tick")
    lost = _lost_saved_semantic_nodes([_sem("old_tick", "tick.sh", "docs/notes.md"), twin], [twin])
    assert [n["id"] for n in lost] == ["old_tick"]


def _saved_keyed_pair(tmp_path: Path) -> Path:
    out = tmp_path / "graph.json"
    out.write_text(json.dumps({"nodes": [_located("a_tick"), _sem("b_tick", "tick.sh", "docs/notes.md")], "links": []}), encoding="utf-8")
    return out


def test_same_file_semantic_fold_to_json_follows_the_build_dedup_flag(tmp_path, capsys):
    # extract --no-dedup keeps same-key duplicates, so a missing one is a real
    # loss; the guard reads the flag build_from_json stamped on the graph.
    extraction = {"nodes": [_located("a_tick")], "edges": []}
    out = _saved_keyed_pair(tmp_path)
    assert to_json(build_from_json(dict(extraction), dedup=False), {}, str(out)) is False
    assert "b_tick" in capsys.readouterr().err
    assert to_json(build_from_json(dict(extraction)), {}, str(out)) is True


def test_same_file_semantic_fold_to_json_fails_closed_without_the_flag(tmp_path):
    import networkx as nx

    out = _saved_keyed_pair(tmp_path)
    G = nx.Graph()
    G.add_node("a_tick", **{k: v for k, v in _located("a_tick").items() if k != "id"})
    assert to_json(G, {}, str(out)) is False


def test_same_file_semantic_fold_check_shrink_does_not_ask_for_the_excuse(tmp_path, monkeypatch):
    import graphify.build as build_mod

    seen: list = []

    def spy(*args, **kwargs):
        seen.append((args, kwargs))
        return []

    monkeypatch.setattr(build_mod, "_lost_saved_semantic_nodes", spy)
    _, existing = _saved_graph(tmp_path, _sem("src_models_user_ts_user", "User", "src/models/user.ts"))
    _check_shrink(force=False, existing_data=existing, new_data=_node_data(build_from_json({"nodes": [], "edges": []})))
    assert len(seen) == 1
    args, kwargs = seen[0]
    assert not kwargs.get("semantic_fold") and len(args) < 5


def test_same_file_semantic_fold_needs_a_saved_twin():
    # Like test_non_ast_replacement_is_not_excused: the twin is new in this run,
    # not a saved duplicate going away, so the loss stands.
    saved = [_sem("old_tick", "tick.sh", "docs/notes.md")]
    lost = _lost_saved_semantic_nodes(saved, [_located("new_tick")], semantic_fold=True)
    assert [n["id"] for n in lost] == ["old_tick"]


def test_same_file_semantic_fold_to_json_writes_reload(tmp_path):
    out = _saved_twin_graph(tmp_path)
    G = build_from_json(json.loads(out.read_text(encoding="utf-8")))
    assert G.number_of_nodes() == 2  # the twins folded on reload
    assert to_json(G, {}, str(out)) is True


def test_same_file_semantic_fold_still_refuses_genuine_loss(tmp_path, capsys):
    out = _saved_twin_graph(tmp_path)
    G = build_from_json({"nodes": [_sem("docs_renamed_md_tick_sh", "tick.sh", "docs/renamed.md")], "edges": []})
    assert to_json(G, {}, str(out)) is False
    assert "docs_renamed_md_other" in capsys.readouterr().err
