import errno
import base64
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

import atlas_worker.bundle as bundle_module
from atlas_worker.bundle import (
    BundleContext,
    SearchDocument,
    build_candidate_bundle,
    promote_bundle,
    validate_bundle,
)
from atlas_worker.cover import ProjectCover
from atlas_worker.manifest import content_version, tree_hash
from atlas_worker.models import (
    ArticleSection,
    BundleManifest,
    DecisionIndexEntry,
    DiagramRef,
    EvidenceRecord,
    GraphData,
    GraphEdge,
    GraphNode,
    ProjectEvent,
    ProjectArticle,
    ProjectSystemMap,
    ProjectMemory,
    PublicProject,
    SystemMapDecisionLink,
    SystemMapFlow,
    SystemMapNode,
)
from atlas_worker.privacy import PrivacyGate, PrivacyViolation
from tests.worker.helpers import (
    make_challenge_events,
    make_public_project,
    refresh_fixture_manifest,
    write_bundle_fixture,
)


ABSOLUTE_PATH_CASES = (
    "/",
    "/tmp/atlas-private",
    "/root/atlas-private",
    "/Users/private/atlas",
    "root:/home/dowon/private",
    r"D:\atlas\private",
    "E:/atlas/private",
    r"\\server\share\atlas",
    "//server/share/atlas",
)
URL_ADJACENT_PATH_PROBES = (
    "https://example.com,/tmp/private",
    "https://example.com);/root/private",
    "prefix</Users/private/atlas",
)
MARKUP_ATTRIBUTE_PATH_PROBES = (
    '<a href="/tmp/private">link</a>',
    r"<div data-path='C:\private\x'>content</div>",
    r"<img src=\\server\share\x>",
    '<div style="background:url(/root/private)">content</div>',
)
MALFORMED_MARKUP_PATH_PROBES = (
    "<div /tmp/private>",
    r"<div C:\private\x>",
    r"<div \\server\share\x>",
)
SAFE_INTERNAL_ANCHOR = '<a href="/projects/alpha?next=/tmp/example#overview">Alpha</a>'
UNSAFE_PUBLIC_ROUTE_LOOKALIKES = (
    '<a href="/projects-archive/alpha">Alpha</a>',
    '<a href="/projects/../tmp">Alpha</a>',
    '<a href="//projects/alpha">Alpha</a>',
    '<a href="/projects%252F..%252Ftmp">Alpha</a>',
    '<div data-route="/projects/alpha">Alpha</div>',
)
LEADING_ENCODED_ROUTE_PROBES = (
    '<a href="%2Ftmp/private">Alpha</a>',
    '<a href="%252Ftmp/private">Alpha</a>',
    '<a href="%5Ctmp%5Cprivate">Alpha</a>',
    '<a href="%255Ctmp%255Cprivate">Alpha</a>',
    '<a href="%2E%2E%2Ftmp">Alpha</a>',
    '<a href="%252E%252E%252Ftmp">Alpha</a>',
    '<a href="%2F%2Fexample.com/projects/alpha">Alpha</a>',
    '<a href="/%2Fexample.com/projects/alpha">Alpha</a>',
    '<a href="docs%2500private">Alpha</a>',
)
UNSAFE_URL_SCHEME_PROBES = (
    '<a href="javascript:alert(1)">Alpha</a>',
    '<a href="  JaVaScRiPt:alert(1)">Alpha</a>',
    '<a href="%6A%61vascript%3Aalert(1)">Alpha</a>',
    '<a href="data:text/plain,atlas">Alpha</a>',
    '<a href="%64ata%3Atext/plain,atlas">Alpha</a>',
    '<a href="vbscript:msgbox(1)">Alpha</a>',
    '<a href="vbscript%3Amsgbox(1)">Alpha</a>',
    '<a href="file:///tmp/private">Alpha</a>',
    '<a href="file%3A%2F%2F%2Ftmp/private">Alpha</a>',
    '<a href="blob:https://example.com/atlas">Alpha</a>',
    '<a href="blob%3Ahttps%3A%2F%2Fexample.com/atlas">Alpha</a>',
    '<a href="custom+atlas:value">Alpha</a>',
    '<a href="custom%2Batlas%3Avalue">Alpha</a>',
)
PRODUCTION_ALIAS_KEY = b"0123456789abcdef0123456789abcdef"


def _context(
    *,
    projects: tuple[PublicProject, ...] | None = None,
    decisions: tuple[str, ...] = ("Keep typed contracts",),
    source_hashes: dict[str, str] | None = None,
    gate: PrivacyGate | None = None,
    previous_manifest: BundleManifest | None = None,
) -> BundleContext:
    projects = projects or (make_public_project("alpha"),)
    memories = {
        project.project_id: ProjectMemory(
            profile=project.to_dict(),
            build_story=("Built the local pipeline",),
            decisions=decisions,
            rollbacks=(),
        )
        for project in projects
    }
    events = {project.project_id: make_challenge_events() for project in projects}
    search_documents = tuple(
        SearchDocument(
            document_id=f"project:{project.project_id}",
            project_id=project.project_id,
            title=project.display_name,
            body=project.summary,
            url=f"/projects/{project.project_id}",
        )
        for project in reversed(projects)
    )
    return BundleContext(
        projects=projects,
        project_memories=memories,
        project_events=events,
        graph=_public_graph(projects),
        search_documents=search_documents,
        source_hashes=source_hashes or {"alpha": "a" * 64},
        previous_manifest=previous_manifest,
        privacy_gate=gate or PrivacyGate(alias_key=b"unit-test-key"),
    )


def _public_graph(projects: tuple[PublicProject, ...]) -> GraphData:
    project_nodes = tuple(
        GraphNode(
            f"project:{project.project_id}",
            project.display_name,
            "Project",
            f"/projects/{project.project_id}",
            project.summary,
        )
        for project in projects
    )
    edges = (
        GraphEdge("focus:delivery", "domain:ai", "FOCUS_HAS_TAG"),
        *(GraphEdge(f"project:{project.project_id}", "focus:delivery", "HAS_FOCUS") for project in projects),
        *(GraphEdge(f"project:{project.project_id}", "domain:ai", "HAS_TAG") for project in projects),
    )
    if len(projects) > 1:
        edges += (
            GraphEdge(
                f"project:{projects[0].project_id}",
                f"project:{projects[1].project_id}",
                "EVOLVED_FROM",
                evidence_links=(
                    {
                        "label": "Routing spec",
                        "url": f"/projects/{projects[0].project_id}?tab=evidence",
                    },
                ),
            ),
        )
    return GraphData(
        nodes=(
            GraphNode("focus:delivery", "Delivery", "KnowledgeFocus"),
            GraphNode("domain:ai", "AI", "KnowledgeDomain"),
            *project_nodes,
        ),
        edges=edges,
    )


def test_candidate_bundle_projects_exact_public_kg_records_and_evidence_links(tmp_path):
    projects = (make_public_project("alpha"), make_public_project("beta"))
    context = replace(_context(projects=projects), graph=_public_graph(projects))

    build_candidate_bundle(context, tmp_path / "candidate")

    nodes = json.loads((tmp_path / "candidate/graph/nodes.json").read_text(encoding="utf-8"))
    edges = json.loads((tmp_path / "candidate/graph/edges.json").read_text(encoding="utf-8"))
    assert all(set(node) == {"id", "label", "kind", "url", "summary"} for node in nodes)
    assert all(
        set(edge) == {"id", "source", "target", "kind", "weight", "evidence_links"}
        for edge in edges
    )
    relation = next(edge for edge in edges if edge["kind"] == "EVOLVED_FROM")
    assert relation["evidence_links"] == [
        {"label": "Routing spec", "url": "/projects/alpha?tab=evidence"}
    ]


def test_bundle_rejects_every_similarity_edge_even_when_rehashed(tmp_path):
    bundle = tmp_path / "candidate"
    project_ids = ("left", "right")
    write_bundle_fixture(bundle, None, "safe", project_ids=project_ids)
    edge_path = bundle / "graph/edges.json"
    edges = json.loads(edge_path.read_text(encoding="utf-8"))
    edges.append(
        {
            "id": "similarity:left:right",
            "source": "project:left",
            "target": "project:right",
            "kind": "project-similarity",
            "weight": 1,
            "evidence_links": [],
        }
    )
    edge_path.write_text(
        json.dumps(edges, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    refresh_fixture_manifest(bundle, None, project_ids)

    with pytest.raises(ValueError, match="graph-edge-kind"):
        validate_bundle(bundle, PrivacyGate(alias_key=b"unit-test-key"))


def test_bundle_rejects_rehashed_private_graph_label(tmp_path):
    bundle = tmp_path / "candidate"
    write_bundle_fixture(bundle, None, "safe")
    node_path = bundle / "graph/nodes.json"
    nodes = json.loads(node_path.read_text(encoding="utf-8"))
    nodes[0]["label"] = "/home/dowon/private"
    node_path.write_text(
        json.dumps(nodes, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    refresh_fixture_manifest(bundle, None, ("alpha",))

    with pytest.raises(PrivacyViolation, match="absolute_path"):
        validate_bundle(bundle, PrivacyGate(alias_key=b"unit-test-key"))


def _article(project_id: str = "alpha") -> ProjectArticle:
    return ProjectArticle(
        project_id=project_id,
        title="Routing decision record",
        summary="Public routing decisions",
        orientation="The routing problem requires a deterministic public contract.",
        orientation_evidence_ids=("routing-proof",),
        readiness="ready",
        sections=(
            ArticleSection(
                section_id="routing",
                title="Routing",
                section_type="decision",
                body="The public routing contract remains deterministic.",
                evidence_ids=("routing-proof",),
                diagrams=(
                    DiagramRef(
                        diagram_id="routing-flow",
                        source_path="project_memory/project-atlas/visuals/routing-flow.svg",
                        caption="Routing flow",
                        alt="Routing flow diagram",
                        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1" /></svg>',
                    ),
                ),
            ),
        ),
    )


def _system_map(project_id: str = "alpha") -> ProjectSystemMap:
    return ProjectSystemMap(
        project_id=project_id,
        map_type="road-recording",
        title="Routing contract map",
        summary="A request crosses validation before it reaches the routed output.",
        nodes=(
            SystemMapNode("request", "Request", "input", "The public request payload."),
            SystemMapNode("router", "Router", "process", "Selects the supported route."),
            SystemMapNode("result", "Result", "output", "The validated routed result."),
        ),
        flows=(
            SystemMapFlow("route", "request", "router", "validate"),
            SystemMapFlow("respond", "router", "result", "emit"),
        ),
        decision_links=(
            SystemMapDecisionLink(("request", "router"), "routing", "Keep routing deterministic"),
        ),
        evidence_ids=("routing-proof",),
    )


def _evidence(project_id: str = "alpha") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="routing-proof",
        project_id=project_id,
        label="Public routing contract",
        source_type="test",
        source_locator="private locator",
        observed_at="2026-08-24T10:00:00Z",
        privacy_class="public-safe",
        content_hash="a" * 64,
    )


def test_bundle_writes_v2_article_and_only_referenced_figures(tmp_path):
    context = replace(
        _context(),
        project_articles={"alpha": _article()},
        project_evidence={"alpha": (_evidence(),)},
    )

    manifest = build_candidate_bundle(context, tmp_path / "candidate")
    project_dir = tmp_path / "candidate" / "projects" / "alpha"
    article = json.loads((project_dir / "article.json").read_text(encoding="utf-8"))

    assert article["sections"][0]["id"] == "routing"
    assert (project_dir / "visuals" / "routing-flow.svg").is_file()
    assert not (project_dir / "decisions.md").exists()
    assert not (project_dir / "visuals" / "problem-solving.svg").exists()
    assert "projects/alpha/article.json" in manifest.files


def test_bundle_writes_reviewed_project_cover_as_public_metadata(tmp_path):
    cover = ProjectCover(
        alt="Alpha implementation screen",
        caption="Actual implementation",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\nfixture",
    )
    context = replace(
        _context(),
        project_articles={"alpha": _article()},
        project_evidence={"alpha": (_evidence(),)},
        project_covers={"alpha": cover},
    )

    manifest = build_candidate_bundle(context, tmp_path / "candidate")
    payload = json.loads(
        (tmp_path / "candidate" / "projects" / "alpha" / "cover.json").read_text(encoding="utf-8")
    )

    assert payload["content_type"] == "image/png"
    assert bytes.fromhex(payload["content_hex"]) == cover.content
    assert "projects/alpha/cover.json" in manifest.files


def test_bundle_writes_structured_system_map_and_generated_svg_together(tmp_path):
    context = replace(
        _context(),
        project_articles={"alpha": _article()},
        project_evidence={"alpha": (_evidence(),)},
        project_system_maps={"alpha": _system_map()},
    )

    manifest = build_candidate_bundle(context, tmp_path / "candidate")
    project_dir = tmp_path / "candidate" / "projects" / "alpha"
    payload = json.loads((project_dir / "system-map.json").read_text(encoding="utf-8"))
    svg = (project_dir / "system-map.svg").read_text(encoding="utf-8")

    assert payload["project_id"] == "alpha"
    assert payload["decision_links"][0]["section_id"] == "routing"
    assert "Routing contract map" in svg
    assert "projects/alpha/system-map.json" in manifest.files
    assert "projects/alpha/system-map.svg" in manifest.files


def test_bundle_rejects_duplicate_article_section_ids(tmp_path):
    article = _article()
    duplicate = replace(article.sections[0], diagrams=())
    context = replace(
        _context(),
        project_articles={"alpha": replace(article, sections=(article.sections[0], duplicate))},
        project_evidence={"alpha": (_evidence(),)},
    )

    with pytest.raises(ValueError, match="section IDs"):
        build_candidate_bundle(context, tmp_path / "candidate")


def test_bundle_rejects_duplicate_article_decision_ids(tmp_path):
    article = _article()
    decision = DecisionIndexEntry("routing-decision", "routing", "adopted", ("routing-proof",))
    context = replace(
        _context(),
        project_articles={"alpha": replace(article, decision_index=(decision, decision))},
        project_evidence={"alpha": (_evidence(),)},
    )

    with pytest.raises(ValueError, match="decision IDs"):
        build_candidate_bundle(context, tmp_path / "candidate")


def test_bundle_rejects_duplicate_section_evidence_references(tmp_path):
    article = _article()
    section = replace(article.sections[0], evidence_ids=("routing-proof", "routing-proof"))
    context = replace(
        _context(),
        project_articles={"alpha": replace(article, sections=(section,))},
        project_evidence={"alpha": (_evidence(),)},
    )

    with pytest.raises(ValueError, match="section evidence references"):
        build_candidate_bundle(context, tmp_path / "candidate")


def test_bundle_rejects_duplicate_decision_evidence_references(tmp_path):
    article = _article()
    decision = DecisionIndexEntry(
        "routing-decision", "routing", "adopted", ("routing-proof", "routing-proof")
    )
    context = replace(
        _context(),
        project_articles={"alpha": replace(article, decision_index=(decision,))},
        project_evidence={"alpha": (_evidence(),)},
    )

    with pytest.raises(ValueError, match="decision evidence references"):
        build_candidate_bundle(context, tmp_path / "candidate")


def test_bundle_rejects_decision_that_does_not_reference_an_article_section(tmp_path):
    article = _article()
    decision = DecisionIndexEntry("routing-decision", "missing-section", "adopted", ("routing-proof",))
    context = replace(
        _context(),
        project_articles={"alpha": replace(article, decision_index=(decision,))},
        project_evidence={"alpha": (_evidence(),)},
    )

    with pytest.raises(ValueError, match="decision section ID"):
        build_candidate_bundle(context, tmp_path / "candidate")


def test_bundle_rejects_duplicate_search_document_ids(tmp_path):
    context = _context()
    context = replace(context, search_documents=(context.search_documents[0], context.search_documents[0]))

    with pytest.raises(ValueError, match="search document IDs"):
        build_candidate_bundle(context, tmp_path / "candidate")


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and not path.is_symlink()
    }


def _symlinked_parent(tmp_path: Path, name: str) -> tuple[Path, Path]:
    real_parent = tmp_path / f"{name}-real"
    real_parent.mkdir()
    linked_parent = tmp_path / name
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    return linked_parent, real_parent


def test_build_emits_only_exact_v2_public_layout_without_unstructured_filler(tmp_path):
    staging = tmp_path / "staging"
    build_candidate_bundle(_context(), staging)

    assert tuple(_tree_bytes(staging)) == (
        "changelog.json",
        "graph/edges.json",
        "graph/nodes.json",
        "manifest.json",
        "projects/alpha/project.json",
        "search-index.json",
        "topics.json",
    )
    assert not (staging / "projects/alpha/decisions.md").exists()


def test_build_omits_public_svg_until_typed_history_has_a_decision_path(tmp_path):
    staging = tmp_path / "staging"
    event = ProjectEvent(
        "decision-only",
        "2026-08-24",
        "Decision",
        "Reviewed evidence",
        "Keep typed events",
        "Decision retained",
        "decision",
    )
    context = replace(_context(), project_events={"alpha": (event,)})

    build_candidate_bundle(context, staging)

    assert not (
        staging / "projects" / "alpha" / "visuals" / "problem-solving.svg"
    ).exists()
    changelog = json.loads((staging / "changelog.json").read_text(encoding="utf-8"))
    assert [entry["event_id"] for entry in changelog] == ["decision-only"]


def test_public_bundle_validation_api_is_read_only(tmp_path):
    fixture = tmp_path / "public-bundle"
    write_bundle_fixture(fixture, version=None, summary="safe")
    before = _tree_bytes(fixture)

    manifest = bundle_module.validate_bundle(fixture, PrivacyGate(alias_key=b"key"))

    assert manifest.projects == ("alpha",)
    assert _tree_bytes(fixture) == before


def test_rehashed_duplicate_search_index_fails_validation_and_preserves_last_good_on_promotion(
    tmp_path,
):
    staging = tmp_path / "staging"
    public_dir = tmp_path / "public-bundle"
    write_bundle_fixture(staging, version=None, summary="candidate")
    write_bundle_fixture(public_dir, version=None, summary="last good")
    search_path = staging / "search-index.json"
    search_index = json.loads(search_path.read_text(encoding="utf-8"))
    search_index.append(dict(search_index[0]))
    search_path.write_text(json.dumps(search_index, sort_keys=True) + "\n", encoding="utf-8")
    refresh_fixture_manifest(staging, None, ("alpha",))
    before = _tree_bytes(public_dir)

    with pytest.raises(ValueError, match="search document IDs must be unique"):
        validate_bundle(staging, PrivacyGate(alias_key=b"key"))
    with pytest.raises(ValueError, match="search document IDs must be unique"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before


def test_validate_bundle_accepts_actual_legacy_v1_graph_records(tmp_path):
    fixture = tmp_path / "public-bundle"
    project_ids = ("alpha", "beta")
    write_bundle_fixture(
        fixture,
        version=None,
        summary="safe",
        project_ids=project_ids,
        format_version=1,
    )
    nodes = json.loads((fixture / "graph/nodes.json").read_text(encoding="utf-8"))
    edges = json.loads((fixture / "graph/edges.json").read_text(encoding="utf-8"))
    legacy = fixture / "projects" / "alpha" / "decisions.md"
    legacy.write_text("# Decisions\n\n- Preserve v1 reads\n", encoding="utf-8")
    refresh_fixture_manifest(fixture, None, project_ids, format_version=1)

    manifest = validate_bundle(fixture, PrivacyGate(alias_key=b"key"))

    assert all(set(node) == {"id", "label", "kind"} for node in nodes)
    assert all(set(edge) == {"source", "target", "kind", "weight", "reasons"} for edge in edges)
    assert any(edge["kind"] == "project-similarity" for edge in edges)
    assert manifest.format_version == 1


def test_validate_bundle_v2_rejects_legacy_graph_records(tmp_path):
    fixture = tmp_path / "public-bundle"
    write_bundle_fixture(fixture, version=None, summary="safe", format_version=1)
    refresh_fixture_manifest(fixture, None, ("alpha",), format_version=2)

    with pytest.raises(ValueError, match="graph node"):
        validate_bundle(fixture, PrivacyGate(alias_key=b"key"))


def test_validate_bundle_rejects_missing_format_version(tmp_path):
    fixture = tmp_path / "public-bundle"
    write_bundle_fixture(fixture, version=None, summary="safe")
    payload = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    del payload["format_version"]
    (fixture / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="format_version"):
        validate_bundle(fixture, PrivacyGate(alias_key=b"key"))


def test_build_rebuilds_staging_from_empty(tmp_path):
    staging = tmp_path / "staging"
    (staging / "raw-session").mkdir(parents=True)
    (staging / "raw-session/session.jsonl").write_text("private", encoding="utf-8")

    build_candidate_bundle(_context(), staging)

    assert not (staging / "raw-session").exists()


def test_manifest_is_schema_exact_content_derived_and_byte_deterministic(tmp_path):
    projects = (make_public_project("beta"), make_public_project("alpha"))
    first = tmp_path / "first"
    second = tmp_path / "second"

    manifest = build_candidate_bundle(_context(projects=projects), first)
    build_candidate_bundle(_context(projects=projects), second)
    payload = json.loads((first / "manifest.json").read_text(encoding="utf-8"))

    assert set(payload) == {"format_version", "version", "projects", "files"}
    assert payload["format_version"] == 2
    assert payload["projects"] == ["alpha", "beta"]
    assert "manifest.json" not in payload["files"]
    assert manifest.project_hashes.keys() == {"alpha", "beta"}
    assert manifest.to_dict() == payload
    assert _tree_bytes(first) == _tree_bytes(second)


def test_manifest_version_ignores_unverifiable_source_hash_metadata(tmp_path):
    first = build_candidate_bundle(
        _context(source_hashes={"/home/dowon/.codex/sessions/raw.jsonl": "a" * 64}),
        tmp_path / "first",
    )
    second = build_candidate_bundle(
        _context(source_hashes={"/home/dowon/.codex/sessions/raw.jsonl": "b" * 64}),
        tmp_path / "second",
    )
    rendered = b"".join(_tree_bytes(tmp_path / "first").values())

    assert first.version == second.version
    assert _tree_bytes(tmp_path / "first") == _tree_bytes(tmp_path / "second")
    assert b"/home/dowon" not in rendered
    assert b"session" not in rendered.lower()
    assert b"provenance" not in rendered.lower()
    assert b"unit-test-key" not in rendered


def test_manifest_version_is_recomputable_from_public_hashes(tmp_path):
    manifest = build_candidate_bundle(_context(), tmp_path / "staging")

    assert manifest.version == content_version(manifest.files, manifest.project_hashes)


def test_non_none_empty_previous_manifest_reports_first_projects(tmp_path):
    previous = BundleManifest(
        version=content_version({}, {}),
        projects=(),
        files={},
        project_hashes={},
    )

    manifest = build_candidate_bundle(
        _context(previous_manifest=previous),
        tmp_path / "staging",
    )

    assert manifest.changed_projects == ("alpha",)


def test_previous_manifest_reports_added_and_keeps_unchanged_project_out(tmp_path):
    previous = build_candidate_bundle(_context(), tmp_path / "previous")
    projects = (make_public_project("alpha"), make_public_project("beta"))

    manifest = build_candidate_bundle(
        _context(projects=projects, previous_manifest=previous),
        tmp_path / "current",
    )

    assert manifest.changed_projects == ("beta",)


def test_previous_manifest_reports_modified_project(tmp_path):
    previous = build_candidate_bundle(_context(), tmp_path / "previous")
    changed = replace(make_public_project("alpha"), summary="Changed public summary")

    manifest = build_candidate_bundle(
        _context(projects=(changed,), previous_manifest=previous),
        tmp_path / "current",
    )

    assert manifest.changed_projects == ("alpha",)


def test_previous_manifest_reports_removed_project(tmp_path):
    projects = (make_public_project("alpha"), make_public_project("beta"))
    previous = build_candidate_bundle(_context(projects=projects), tmp_path / "previous")

    manifest = build_candidate_bundle(
        _context(previous_manifest=previous),
        tmp_path / "current",
    )

    assert manifest.changed_projects == ("beta",)


def test_previous_manifest_noop_reports_no_changed_projects(tmp_path):
    previous = build_candidate_bundle(_context(), tmp_path / "previous")

    manifest = build_candidate_bundle(
        _context(previous_manifest=previous),
        tmp_path / "current",
    )

    assert manifest.changed_projects == ()


def test_stale_previous_manifest_is_rejected_explicitly(tmp_path):
    previous = build_candidate_bundle(_context(), tmp_path / "previous")
    stale = replace(previous, project_hashes={"alpha": "0" * 64})

    with pytest.raises(ValueError, match="previous manifest"):
        build_candidate_bundle(
            _context(previous_manifest=stale),
            tmp_path / "current",
        )


def test_previous_manifest_with_stale_version_is_rejected_explicitly(tmp_path):
    previous = build_candidate_bundle(_context(), tmp_path / "previous")
    stale = replace(previous, version="0" * 64)

    with pytest.raises(ValueError, match="previous manifest"):
        build_candidate_bundle(
            _context(previous_manifest=stale),
            tmp_path / "current",
        )


def test_previous_manifest_with_impossible_public_layout_is_rejected(tmp_path):
    previous = build_candidate_bundle(_context(), tmp_path / "previous")
    stale_files = {**previous.files, "raw-session.jsonl": "0" * 64}
    stale = replace(
        previous,
        files=stale_files,
        version=content_version(stale_files, previous.project_hashes),
    )

    with pytest.raises(ValueError, match="previous manifest"):
        build_candidate_bundle(
            _context(previous_manifest=stale),
            tmp_path / "current",
        )


def test_build_omits_legacy_memory_even_when_it_contains_managed_comments(tmp_path):
    context = _context(
        decisions=(
            "<!-- atlas:event:decision-001 -->\nKeep typed contracts\n<!-- /atlas:event:decision-001 -->",
        )
    )

    build_candidate_bundle(context, tmp_path / "staging")
    assert not (tmp_path / "staging/projects/alpha/decisions.md").exists()


def test_build_blocks_arbitrary_html_comments(tmp_path):
    article = _article()
    context = replace(
        _context(),
        project_articles={
            "alpha": replace(article, sections=(replace(article.sections[0], body="Keep this <!-- author note --> private"),))
        },
        project_evidence={"alpha": (_evidence(),)},
    )

    with pytest.raises(PrivacyViolation, match="html_comment"):
        build_candidate_bundle(context, tmp_path / "staging")


@pytest.mark.parametrize("local_path", ABSOLUTE_PATH_CASES)
def test_build_rejects_every_absolute_path_family(tmp_path, local_path):
    project = replace(make_public_project("alpha"), summary=local_path)

    with pytest.raises(PrivacyViolation, match="absolute_path") as error:
        build_candidate_bundle(_context(projects=(project,)), tmp_path / "staging")

    assert local_path not in str(error.value)


@pytest.mark.parametrize("probe", URL_ADJACENT_PATH_PROBES)
def test_build_rejects_url_delimiter_adjacent_local_paths(tmp_path, probe):
    project = replace(make_public_project("alpha"), summary=probe)

    with pytest.raises(PrivacyViolation, match="absolute_path") as error:
        build_candidate_bundle(_context(projects=(project,)), tmp_path / "staging")

    assert probe not in str(error.value)


@pytest.mark.parametrize("probe", MARKUP_ATTRIBUTE_PATH_PROBES)
def test_build_rejects_markup_attribute_paths_without_candidate_leak(tmp_path, probe):
    staging = tmp_path / "staging"
    project = replace(make_public_project("alpha"), summary=probe)

    with pytest.raises(PrivacyViolation) as error:
        build_candidate_bundle(_context(projects=(project,)), staging)

    assert str(error.value) == "public bundle blocked: absolute_path"
    assert probe not in str(error.value)
    assert _tree_bytes(staging) == {}


@pytest.mark.parametrize("probe", MALFORMED_MARKUP_PATH_PROBES)
def test_build_rejects_malformed_markup_paths_without_candidate_leak(tmp_path, probe):
    staging = tmp_path / "staging"
    project = replace(make_public_project("alpha"), summary=probe)

    with pytest.raises(PrivacyViolation) as error:
        build_candidate_bundle(_context(projects=(project,)), staging)

    assert str(error.value) == "public bundle blocked: absolute_path"
    assert probe not in str(error.value)
    assert _tree_bytes(staging) == {}


def test_build_allows_public_urls_in_markup_attributes_and_visible_text(tmp_path):
    summary = (
        '<a href="https://example.com/docs/path?q=/tmp/example#top">'
        "Visible https://example.com/public/path</a>"
    )
    project = replace(make_public_project("alpha"), summary=summary)

    build_candidate_bundle(_context(projects=(project,)), tmp_path / "staging")

    payload = json.loads((tmp_path / "staging/projects/alpha/project.json").read_text(encoding="utf-8"))
    assert payload["summary"] == summary


def test_build_preserves_safe_internal_anchor_in_public_json(tmp_path):
    staging = tmp_path / "staging"
    project = replace(make_public_project("alpha"), summary=SAFE_INTERNAL_ANCHOR)

    build_candidate_bundle(_context(projects=(project,)), staging)

    payload = json.loads((staging / "projects/alpha/project.json").read_text(encoding="utf-8"))
    assert payload["summary"] == SAFE_INTERNAL_ANCHOR


@pytest.mark.parametrize("probe", LEADING_ENCODED_ROUTE_PROBES)
def test_build_rejects_leading_encoded_route_markers_without_candidate_leak(tmp_path, probe):
    staging = tmp_path / "staging"
    project = replace(make_public_project("alpha"), summary=probe)

    with pytest.raises(PrivacyViolation) as error:
        build_candidate_bundle(_context(projects=(project,)), staging)

    assert str(error.value) == "public bundle blocked: absolute_path"
    assert probe not in str(error.value)
    assert _tree_bytes(staging) == {}


@pytest.mark.parametrize("probe", UNSAFE_URL_SCHEME_PROBES)
def test_build_rejects_non_http_url_schemes_without_candidate_leak(tmp_path, probe):
    staging = tmp_path / "staging"
    project = replace(make_public_project("alpha"), summary=probe)

    with pytest.raises(PrivacyViolation) as error:
        build_candidate_bundle(_context(projects=(project,)), staging)

    assert str(error.value) == "public bundle blocked: absolute_path"
    assert probe not in str(error.value)
    assert _tree_bytes(staging) == {}


def test_build_rejects_existing_staging_symlink_before_cleanup(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        build_candidate_bundle(_context(), staging)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_build_rejects_staging_ancestor_symlink_before_cleanup(tmp_path):
    linked_parent, real_parent = _symlinked_parent(tmp_path, "linked-staging-parent")
    staging = linked_parent / "staging"
    write_bundle_fixture(staging, version=None, summary="safe")
    before = _tree_bytes(real_parent / "staging")

    with pytest.raises(ValueError, match="symlink"):
        build_candidate_bundle(_context(), staging)

    assert _tree_bytes(real_parent / "staging") == before


def test_build_scans_every_artifact_and_complete_staging_tree(tmp_path):
    class TrackingGate(PrivacyGate):
        def __init__(self):
            super().__init__(alias_key=b"key")
            self.records = []

        def require_safe(self, record: object) -> None:
            self.records.append(record)
            super().require_safe(record)

    gate = TrackingGate()
    staging = tmp_path / "staging"

    build_candidate_bundle(_context(gate=gate), staging)

    artifact_count = len(_tree_bytes(staging))
    assert len(gate.records) == artifact_count + 1
    assert isinstance(gate.records[-1], dict)
    assert tuple(gate.records[-1]) == tuple(_tree_bytes(staging))


def test_first_publish_reports_all_projects(tmp_path):
    projects = (make_public_project("beta"), make_public_project("alpha"))
    staging = tmp_path / "staging"
    build_candidate_bundle(_context(projects=projects), staging)

    result = promote_bundle(staging, tmp_path / "public-bundle", PrivacyGate(alias_key=b"key"))

    assert result.changed
    assert result.changed_projects == ("alpha", "beta")
    assert not staging.exists()


def test_changed_and_removed_projects_are_reported_in_sorted_order(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, None, "old summary", ("alpha", "beta", "gamma"))
    write_bundle_fixture(staging, None, "new summary", ("beta",))

    result = promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert result.changed_projects == ("alpha", "beta", "gamma")


def test_identical_candidate_is_noop_and_preserves_public_inode_and_bytes(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version=None, summary="safe")
    write_bundle_fixture(staging, version=None, summary="safe")
    before = _tree_bytes(public_dir)
    inode = public_dir.stat().st_ino

    result = promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert not result.changed
    assert result.changed_projects == ()
    assert public_dir.stat().st_ino == inode
    assert _tree_bytes(public_dir) == before
    assert staging.exists()


def test_privacy_failure_preserves_last_good_bundle(tmp_path):
    public_dir = tmp_path / "public-bundle"
    write_bundle_fixture(public_dir, version=None, summary="safe")
    staging = tmp_path / "staging"
    write_bundle_fixture(staging, version=None, summary="/home/dowon/private")
    before = _tree_bytes(public_dir)

    with pytest.raises(PrivacyViolation):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before


@pytest.mark.parametrize("local_path", ABSOLUTE_PATH_CASES)
def test_promote_rejects_every_absolute_path_family_and_preserves_last_good(tmp_path, local_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version=None, summary="safe")
    write_bundle_fixture(staging, version=None, summary=local_path)
    before = _tree_bytes(public_dir)

    with pytest.raises(PrivacyViolation, match="absolute_path") as error:
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert local_path not in str(error.value)
    assert _tree_bytes(public_dir) == before


@pytest.mark.parametrize("probe", URL_ADJACENT_PATH_PROBES)
def test_promote_rejects_url_delimiter_adjacent_paths_and_preserves_last_good(tmp_path, probe):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version=None, summary="safe")
    write_bundle_fixture(staging, version=None, summary=probe)
    before = _tree_bytes(public_dir)

    with pytest.raises(PrivacyViolation, match="absolute_path") as error:
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert probe not in str(error.value)
    assert _tree_bytes(public_dir) == before


@pytest.mark.parametrize("probe", MARKUP_ATTRIBUTE_PATH_PROBES)
def test_promote_rejects_markup_attribute_paths_and_preserves_last_good(tmp_path, probe):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version=None, summary="safe")
    write_bundle_fixture(staging, version=None, summary=probe)
    public_before = _tree_bytes(public_dir)
    staging_before = _tree_bytes(staging)

    with pytest.raises(PrivacyViolation) as error:
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert str(error.value) == "public bundle blocked: absolute_path"
    assert probe not in str(error.value)
    assert _tree_bytes(public_dir) == public_before
    assert _tree_bytes(staging) == staging_before


@pytest.mark.parametrize("probe", MALFORMED_MARKUP_PATH_PROBES)
def test_promote_rejects_malformed_markup_paths_and_preserves_last_good(tmp_path, probe):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version=None, summary="safe")
    write_bundle_fixture(staging, version=None, summary=probe)
    public_before = _tree_bytes(public_dir)
    staging_before = _tree_bytes(staging)

    with pytest.raises(PrivacyViolation) as error:
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert str(error.value) == "public bundle blocked: absolute_path"
    assert probe not in str(error.value)
    assert _tree_bytes(public_dir) == public_before
    assert _tree_bytes(staging) == staging_before


def test_safe_internal_anchor_can_publish_and_then_noop(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(staging, version=None, summary=SAFE_INTERNAL_ANCHOR)

    published = promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert published.changed
    payload = json.loads((public_dir / "projects/alpha/project.json").read_text(encoding="utf-8"))
    assert payload["summary"] == SAFE_INTERNAL_ANCHOR

    public_before = _tree_bytes(public_dir)
    public_inode = public_dir.stat().st_ino
    write_bundle_fixture(staging, version=None, summary=SAFE_INTERNAL_ANCHOR)

    no_op = promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert not no_op.changed
    assert no_op.changed_projects == ()
    assert public_dir.stat().st_ino == public_inode
    assert _tree_bytes(public_dir) == public_before
    assert staging.exists()


@pytest.mark.parametrize("probe", UNSAFE_PUBLIC_ROUTE_LOOKALIKES)
def test_promote_rejects_unsafe_route_lookalikes_and_preserves_last_good(tmp_path, probe):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version=None, summary="safe")
    write_bundle_fixture(staging, version=None, summary=probe)
    public_before = _tree_bytes(public_dir)
    staging_before = _tree_bytes(staging)

    with pytest.raises(PrivacyViolation) as error:
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert str(error.value) == "public bundle blocked: absolute_path"
    assert probe not in str(error.value)
    assert _tree_bytes(public_dir) == public_before
    assert _tree_bytes(staging) == staging_before


@pytest.mark.parametrize("probe", LEADING_ENCODED_ROUTE_PROBES)
def test_promote_rejects_leading_encoded_route_markers_and_preserves_last_good(tmp_path, probe):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version=None, summary="safe")
    write_bundle_fixture(staging, version=None, summary=probe)
    public_before = _tree_bytes(public_dir)
    staging_before = _tree_bytes(staging)

    with pytest.raises(PrivacyViolation) as error:
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert str(error.value) == "public bundle blocked: absolute_path"
    assert probe not in str(error.value)
    assert _tree_bytes(public_dir) == public_before
    assert _tree_bytes(staging) == staging_before


@pytest.mark.parametrize("probe", UNSAFE_URL_SCHEME_PROBES)
def test_promote_rejects_non_http_url_schemes_and_preserves_last_good(tmp_path, probe):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version=None, summary="last good")
    write_bundle_fixture(staging, version=None, summary=probe)
    public_before = _tree_bytes(public_dir)
    staging_before = _tree_bytes(staging)

    with pytest.raises(PrivacyViolation) as error:
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert str(error.value) == "public bundle blocked: absolute_path"
    assert probe not in str(error.value)
    assert _tree_bytes(public_dir) == public_before
    assert _tree_bytes(staging) == staging_before


def test_full_tree_scan_preserves_duplicate_json_values_for_privacy(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, None, "safe")
    write_bundle_fixture(staging, None, "safe")
    project_path = staging / "projects/alpha/project.json"
    rendered = project_path.read_text(encoding="utf-8").replace(
        '"summary":"safe"',
        '"summary":"/home/dowon/private","summary":"safe"',
    )
    project_path.write_text(rendered, encoding="utf-8")
    refresh_fixture_manifest(staging, None, ("alpha",))
    before = _tree_bytes(public_dir)

    with pytest.raises(PrivacyViolation, match="absolute_path"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before


def test_schema_failure_preserves_last_good_bundle(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, None, "safe")
    write_bundle_fixture(staging, None, "safe")
    project_path = staging / "projects/alpha/project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project.pop("tags")
    project_path.write_text(json.dumps(project, sort_keys=True) + "\n", encoding="utf-8")
    refresh_fixture_manifest(staging, None, ("alpha",))
    before = _tree_bytes(public_dir)

    with pytest.raises(ValueError, match="tags"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before


@pytest.mark.parametrize(
    "invalid_version",
    ("2026-08-25T10:00:00Z", "0" * 64),
)
def test_invalid_or_time_like_version_preserves_last_good_bundle(tmp_path, invalid_version):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    refresh_fixture_manifest(staging, invalid_version, ("alpha",))
    before = _tree_bytes(public_dir)

    with pytest.raises(ValueError, match="content-derived"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before


def test_candidate_symlink_is_rejected_without_touching_public(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, None, "safe")
    write_bundle_fixture(staging, None, "safe")
    (staging / "projects/alpha/leak.md").symlink_to(public_dir / "manifest.json")
    before = _tree_bytes(public_dir)

    with pytest.raises(ValueError, match="symlink"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before


def test_promote_rejects_staging_ancestor_symlink_before_read(tmp_path):
    linked_parent, _ = _symlinked_parent(tmp_path, "linked-staging-parent")
    staging = linked_parent / "staging"
    public_dir = tmp_path / "public-bundle"
    write_bundle_fixture(staging, version=None, summary="safe")

    with pytest.raises(ValueError, match="symlink"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert not public_dir.exists()


def test_promote_rejects_public_ancestor_symlink_before_read(tmp_path):
    linked_parent, real_parent = _symlinked_parent(tmp_path, "linked-public-parent")
    public_dir = linked_parent / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version=None, summary="old")
    write_bundle_fixture(staging, version=None, summary="new")
    before = _tree_bytes(real_parent / "public-bundle")

    with pytest.raises(ValueError, match="symlink"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(real_parent / "public-bundle") == before


def test_noop_rejects_public_ancestor_symlink_before_hash(tmp_path):
    linked_parent, real_parent = _symlinked_parent(tmp_path, "linked-public-parent")
    public_dir = linked_parent / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version=None, summary="safe")
    write_bundle_fixture(staging, version=None, summary="safe")
    before = _tree_bytes(real_parent / "public-bundle")

    with pytest.raises(ValueError, match="symlink"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(real_parent / "public-bundle") == before


def test_rename_failure_restores_prior_public_bundle(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    before = _tree_bytes(public_dir)
    real_rename = bundle_module._rename
    calls = 0

    def fail_candidate_rename(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected candidate rename failure")
        real_rename(source, target)

    monkeypatch.setattr(bundle_module, "_rename", fail_candidate_rename)

    with pytest.raises(OSError, match="injected"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before
    assert not (tmp_path / ".public-bundle.previous").exists()


def test_candidate_symlink_precondition_failure_restores_previous_bundle(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    before = _tree_bytes(public_dir)
    real_rename = bundle_module._rename

    def fail_candidate_rename(source: Path, target: Path) -> None:
        if source == staging and target == public_dir:
            raise ValueError("injected symlink precondition failure")
        real_rename(source, target)

    monkeypatch.setattr(bundle_module, "_rename", fail_candidate_rename)

    with pytest.raises(ValueError, match="symlink precondition"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before
    assert not (tmp_path / ".public-bundle.previous").exists()


def test_public_to_backup_rename_failure_keeps_live_last_good(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    backup = tmp_path / ".public-bundle.previous"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    before = _tree_bytes(public_dir)
    real_rename = bundle_module._rename

    def fail_first_rename(source: Path, target: Path) -> None:
        if source == public_dir and target == backup:
            raise OSError("injected public to backup failure")
        real_rename(source, target)

    monkeypatch.setattr(bundle_module, "_rename", fail_first_rename)

    with pytest.raises(OSError, match="public to backup"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before
    assert not backup.exists()


def test_backup_restore_failure_recovers_via_validated_atomic_temp(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    backup = tmp_path / ".public-bundle.previous"
    recovery = tmp_path / ".public-bundle.recovery"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    before = _tree_bytes(public_dir)
    real_rename = bundle_module._rename
    copy_targets = []

    def fail_candidate_and_backup_restore(source: Path, target: Path) -> None:
        if (source, target) in ((staging, public_dir), (backup, public_dir)):
            raise OSError("injected restore path failure")
        real_rename(source, target)

    def track_copy(source: Path, target: Path) -> None:
        copy_targets.append(target)
        shutil.copytree(source, target, symlinks=True)

    monkeypatch.setattr(bundle_module, "_rename", fail_candidate_and_backup_restore)
    monkeypatch.setattr(bundle_module, "_copytree", track_copy, raising=False)

    with pytest.raises(OSError, match="restore path"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert copy_targets == [recovery]
    assert public_dir.exists()
    assert _tree_bytes(public_dir) == before
    assert not recovery.exists()


def test_recovery_copy_failure_preserves_intact_backup_and_no_partial_live(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    backup = tmp_path / ".public-bundle.previous"
    recovery = tmp_path / ".public-bundle.recovery"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    before = _tree_bytes(public_dir)
    real_rename = bundle_module._rename

    def fail_candidate_and_backup_restore(source: Path, target: Path) -> None:
        if (source, target) in ((staging, public_dir), (backup, public_dir)):
            raise OSError("injected restore path failure")
        real_rename(source, target)

    def fail_recovery_copy(source: Path, target: Path) -> None:
        target.mkdir()
        (target / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError("injected recovery copy failure")

    monkeypatch.setattr(bundle_module, "_rename", fail_candidate_and_backup_restore)
    monkeypatch.setattr(bundle_module, "_copytree", fail_recovery_copy, raising=False)

    with pytest.raises(bundle_module.BundleRecoveryError, match="recovery copy"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert not public_dir.exists()
    assert _tree_bytes(backup) == before
    assert not recovery.exists()


def test_recovery_failures_use_a_dedicated_oserror_contract():
    assert issubclass(bundle_module.BundleRecoveryError, OSError)
    assert not issubclass(bundle_module.BundleRecoveryError, RuntimeError)


def test_recovery_rename_failure_preserves_intact_backup_and_no_partial_live(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    backup = tmp_path / ".public-bundle.previous"
    recovery = tmp_path / ".public-bundle.recovery"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    before = _tree_bytes(public_dir)
    real_rename = bundle_module._rename

    def fail_restore_renames(source: Path, target: Path) -> None:
        if (source, target) in (
            (staging, public_dir),
            (backup, public_dir),
            (recovery, public_dir),
        ):
            raise OSError("injected recovery rename failure")
        real_rename(source, target)

    monkeypatch.setattr(bundle_module, "_rename", fail_restore_renames)

    with pytest.raises(bundle_module.BundleRecoveryError, match="recovery rename"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert not public_dir.exists()
    assert _tree_bytes(backup) == before
    assert not recovery.exists()


def test_recovery_copy_is_validated_and_hashed_before_live_rename(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    backup = tmp_path / ".public-bundle.previous"
    recovery = tmp_path / ".public-bundle.recovery"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    before = _tree_bytes(public_dir)
    real_rename = bundle_module._rename

    def fail_candidate_and_backup_restore(source: Path, target: Path) -> None:
        if (source, target) in ((staging, public_dir), (backup, public_dir)):
            raise OSError("injected restore path failure")
        real_rename(source, target)

    def copy_then_tamper(source: Path, target: Path) -> None:
        shutil.copytree(source, target, symlinks=True)
        project = target / "projects/alpha/project.json"
        project.write_bytes(project.read_bytes() + b" ")

    monkeypatch.setattr(bundle_module, "_rename", fail_candidate_and_backup_restore)
    monkeypatch.setattr(bundle_module, "_copytree", copy_then_tamper)

    with pytest.raises(bundle_module.BundleRecoveryError, match="recovery validation"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert not public_dir.exists()
    assert _tree_bytes(backup) == before
    assert not recovery.exists()


def test_backup_cleanup_failure_keeps_complete_public_and_intact_backup(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    backup = tmp_path / ".public-bundle.previous"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    before = _tree_bytes(public_dir)
    candidate = _tree_bytes(staging)

    def fail_cleanup(path: Path) -> None:
        raise OSError("injected cleanup failure")

    monkeypatch.setattr(bundle_module, "_cleanup_tree", fail_cleanup, raising=False)

    result = promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert result.changed
    assert _tree_bytes(public_dir) == candidate
    assert _tree_bytes(backup) == before


def test_stale_backup_is_not_overwritten(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    backup = tmp_path / ".public-bundle.previous"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    write_bundle_fixture(backup, None, "older")
    backup_before = _tree_bytes(backup)
    public_before = _tree_bytes(public_dir)

    with pytest.raises(FileExistsError, match="stale backup"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(backup) == backup_before
    assert _tree_bytes(public_dir) == public_before


def test_stale_backup_blocks_identical_noop_without_touching_public_or_staging(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    backup = tmp_path / ".public-bundle.previous"
    write_bundle_fixture(public_dir, None, "same")
    write_bundle_fixture(staging, None, "same")
    write_bundle_fixture(backup, None, "older")
    public_before = _tree_bytes(public_dir)
    staging_before = _tree_bytes(staging)
    backup_before = _tree_bytes(backup)
    public_inode = public_dir.stat().st_ino
    staging_inode = staging.stat().st_ino

    with pytest.raises(FileExistsError, match="stale backup"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert public_dir.stat().st_ino == public_inode
    assert staging.stat().st_ino == staging_inode
    assert _tree_bytes(public_dir) == public_before
    assert _tree_bytes(staging) == staging_before
    assert _tree_bytes(backup) == backup_before


def test_cross_filesystem_device_mismatch_blocks_before_public_rename(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    public_before = _tree_bytes(public_dir)
    staging_before = _tree_bytes(staging)
    real_stat = Path.stat
    rename_calls = []

    def mismatched_device_stat(path: Path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if path == staging:
            values = list(result)
            values[2] = result.st_dev + 1
            return os.stat_result(values)
        return result

    def track_rename(source: Path, target: Path) -> None:
        rename_calls.append((source, target))
        raise AssertionError("rename must not run across filesystems")

    monkeypatch.setattr(Path, "stat", mismatched_device_stat)
    monkeypatch.setattr(bundle_module, "_rename", track_rename)

    with pytest.raises(OSError, match="same filesystem"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert rename_calls == []
    assert _tree_bytes(public_dir) == public_before
    assert _tree_bytes(staging) == staging_before
    assert not (tmp_path / ".public-bundle.previous").exists()


def test_exdev_at_first_rename_preserves_last_good_public(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    backup = tmp_path / ".public-bundle.previous"
    write_bundle_fixture(public_dir, None, "old")
    write_bundle_fixture(staging, None, "new")
    public_before = _tree_bytes(public_dir)
    staging_before = _tree_bytes(staging)
    rename_calls = []

    def fail_cross_device_rename(source: Path, target: Path) -> None:
        rename_calls.append((source, target))
        raise OSError(errno.EXDEV, "injected cross-device rename")

    monkeypatch.setattr(bundle_module, "_rename", fail_cross_device_rename)

    with pytest.raises(OSError) as error:
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert error.value.errno == errno.EXDEV
    assert rename_calls == [(public_dir, backup)]
    assert _tree_bytes(public_dir) == public_before
    assert _tree_bytes(staging) == staging_before
    assert not backup.exists()


def test_tree_hash_uses_relative_paths_and_bytes_not_mtime(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_bundle_fixture(first, None, "safe")
    write_bundle_fixture(second, None, "safe")
    for path in second.rglob("*"):
        if path.is_file():
            os.utime(path, (1, 1))

    assert tree_hash(first) == tree_hash(second)


def test_promotion_rejects_unexpected_files_and_hash_mismatch(tmp_path):
    staging = tmp_path / "staging"
    write_bundle_fixture(staging, None, "safe")
    (staging / "raw.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected"):
        promote_bundle(staging, tmp_path / "public-bundle", PrivacyGate(alias_key=b"key"))


def test_promotion_rejects_legacy_artifacts_from_a_v2_candidate(tmp_path):
    staging = tmp_path / "staging"
    write_bundle_fixture(staging, None, "safe")
    (staging / "projects/alpha/decisions.md").write_text("", encoding="utf-8")
    refresh_fixture_manifest(staging, None, ("alpha",))

    with pytest.raises(ValueError, match="unexpected"):
        promote_bundle(staging, tmp_path / "public-bundle", PrivacyGate(alias_key=b"key"))


def test_bundle_manifest_serialization_excludes_local_project_hashes():
    manifest = BundleManifest(
        version="v1",
        projects=("alpha",),
        files={"projects/alpha/project.json": "hash"},
        project_hashes={"alpha": "local-only"},
        changed_projects=("alpha",),
    )

    assert manifest.to_dict() == {
        "format_version": 2,
        "version": "v1",
        "projects": ["alpha"],
        "files": {"projects/alpha/project.json": "hash"},
    }


def test_candidate_builder_blocks_encoded_alias_key_without_staging_leak(tmp_path):
    encoded_key = base64.urlsafe_b64encode(PRODUCTION_ALIAS_KEY).decode("ascii").rstrip("=")
    project = replace(
        make_public_project("alpha"),
        summary=f"prefix:{encoded_key}:suffix",
    )
    staging = tmp_path / "staging"

    with pytest.raises(PrivacyViolation, match="alias_key") as caught:
        build_candidate_bundle(
            _context(
                projects=(project,),
                gate=PrivacyGate(alias_key=PRODUCTION_ALIAS_KEY),
            ),
            staging,
        )

    assert encoded_key not in str(caught.value)
    assert all(encoded_key.encode("utf-8") not in payload for payload in _tree_bytes(staging).values())


def test_promoter_blocks_alias_key_hex_and_preserves_last_good(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, None, "last good")
    write_bundle_fixture(staging, None, f"prefix:{PRODUCTION_ALIAS_KEY.hex().upper()}:suffix")
    before = _tree_bytes(public_dir)

    with pytest.raises(PrivacyViolation, match="alias_key") as caught:
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=PRODUCTION_ALIAS_KEY))

    assert PRODUCTION_ALIAS_KEY.hex().upper() not in str(caught.value)
    assert _tree_bytes(public_dir) == before


def _malform_graph(root: Path, mutation: str) -> None:
    nodes_path = root / "graph" / "nodes.json"
    edges_path = root / "graph" / "edges.json"
    nodes = json.loads(nodes_path.read_text(encoding="utf-8"))
    edges = json.loads(edges_path.read_text(encoding="utf-8"))
    project_ids = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["projects"]

    if mutation == "similarity-edge":
        edges.append(
            {
                "id": "similarity:left:right",
                "source": f"project:{project_ids[0]}",
                "target": f"project:{project_ids[1]}",
                "kind": "project-similarity",
                "weight": 1,
                "evidence_links": [],
            }
        )
    elif mutation == "dangling-endpoint":
        edges[0]["target"] = "domain:missing"
    elif mutation == "duplicate-node-id":
        nodes.append(dict(nodes[0]))
    elif mutation == "duplicate-edge-pair":
        edges.append(dict(edges[0]))
    elif mutation == "noncanonical-project-id":
        node = next(node for node in nodes if node["id"] == f"project:{project_ids[0]}")
        replacement = f"project:{project_ids[0]}%41"
        original = node["id"]
        node["id"] = replacement
        for edge in edges:
            if edge["source"] == original:
                edge["source"] = replacement
            if edge["target"] == original:
                edge["target"] = replacement
    elif mutation == "unsafe-evidence-link":
        edges[0]["evidence_links"] = [
            {"label": "Private", "url": "javascript:alert(1)"}
        ]
    elif mutation == "invalid-edge-id":
        edges[0]["id"] = "not-canonical"
    elif mutation == "project-metadata":
        project = next(node for node in nodes if node["kind"] == "Project")
        project["summary"] = "mismatched summary"
    else:
        raise AssertionError(f"unknown mutation: {mutation}")

    nodes_path.write_text(
        json.dumps(nodes, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    edges_path.write_text(
        json.dumps(edges, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    refresh_fixture_manifest(root, None, tuple(project_ids))


@pytest.mark.parametrize(
    "mutation",
    (
        "dangling-endpoint",
        "similarity-edge",
        "duplicate-node-id",
        "duplicate-edge-pair",
        "noncanonical-project-id",
        "unsafe-evidence-link",
        "invalid-edge-id",
        "project-metadata",
    ),
)
def test_rehashed_malformed_graph_fails_validation_and_preserves_last_good_on_promotion(
    tmp_path, mutation
):
    project_ids = tuple(f"project-{index}" for index in range(7))
    staging = tmp_path / "staging"
    public = tmp_path / "public-bundle"
    write_bundle_fixture(staging, None, "candidate", project_ids=project_ids)
    write_bundle_fixture(public, None, "last good", project_ids=project_ids)
    _malform_graph(staging, mutation)
    before = _tree_bytes(public)

    with pytest.raises(ValueError, match="graph"):
        validate_bundle(staging, PrivacyGate(alias_key=b"key"))
    with pytest.raises(ValueError, match="graph"):
        promote_bundle(staging, public, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public) == before


@pytest.mark.parametrize("malformation", ("dangling", "project-metadata"))
def test_candidate_build_cross_validates_graph_against_projects(tmp_path, malformation):
    projects = tuple(make_public_project(f"project-{index}") for index in range(7))
    graph = _public_graph(projects)
    if malformation == "dangling":
        graph = GraphData(
            nodes=graph.nodes,
            edges=graph.edges
            + (
                GraphEdge(
                    "project:project-0",
                    "project:missing",
                    "EVOLVED_FROM",
                ),
            ),
        )
    else:
        nodes = tuple(
            replace(node, summary="mismatched summary")
            if node.node_id == "project:project-0"
            else node
            for node in graph.nodes
        )
        graph = GraphData(
            nodes=nodes,
            edges=graph.edges,
        )

    with pytest.raises(ValueError, match="graph"):
        build_candidate_bundle(
            replace(_context(projects=projects), graph=graph),
            tmp_path / "staging",
        )
