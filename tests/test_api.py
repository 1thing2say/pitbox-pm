"""End-to-end tests against a throwaway database.

These cover the parts that are genuinely easy to get wrong: keeping the
materialized path consistent through moves, resolving cascading tags, deep
copying a tree, and file versioning. Run with:  .venv/Scripts/python -m pytest
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a temp database + storage dir BEFORE importing it, since
# config.Settings is read at import time.
_TMP = Path(tempfile.mkdtemp(prefix="pitbox-test-"))
os.environ["PITBOX_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["PITBOX_STORAGE_DIR"] = str(_TMP / "storage")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def project(client):
    r = client.post("/api/projects", json={"name": "Test Car", "season": "2027", "template": "blank"})
    assert r.status_code == 201, r.text
    return r.json()


def _tree(client, project_id):
    r = client.get(f"/api/projects/{project_id}/tree")
    assert r.status_code == 200, r.text
    return r.json()


def _add(client, project_id, parent_id, name, **kw):
    r = client.post(
        "/api/nodes",
        json={"project_id": project_id, "parent_id": parent_id, "name": name, **kw},
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- structure ---------------------------------------------------------------

def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_new_project_from_template_is_populated(client):
    r = client.post("/api/projects", json={"name": "Template Car", "template": "baja_standard"})
    assert r.status_code == 201
    data = _tree(client, r.json()["id"])
    names = {n["name"] for n in data["nodes"]}
    assert "Front Suspension" in names
    assert "Wiring Harness" in names
    root = [n for n in data["nodes"] if n["parent_id"] is None][0]
    assert root["path"] == f"/{root['id']}/"
    assert root["depth"] == 0


def test_path_and_depth_are_maintained_on_insert(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    sub = _add(client, project["id"], root["id"], "Drivetrain", node_type="subsystem")
    part = _add(client, project["id"], sub["id"], "Gearbox", node_type="part")

    assert sub["path"] == f"{root['path']}{sub['id']}/"
    assert part["path"] == f"{root['path']}{sub['id']}/{part['id']}/"
    assert part["depth"] == 2
    assert part["ancestor_ids"] == [root["id"], sub["id"]]


def test_move_rewrites_descendant_paths(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    a = _add(client, project["id"], root["id"], "Branch A")
    b = _add(client, project["id"], root["id"], "Branch B")
    child = _add(client, project["id"], a["id"], "Child")
    grandchild = _add(client, project["id"], child["id"], "Grandchild")

    r = client.post(f"/api/nodes/{child['id']}/move", json={"new_parent_id": b["id"]})
    assert r.status_code == 200, r.text

    nodes = {n["id"]: n for n in _tree(client, project["id"])["nodes"]}
    moved, moved_gc = nodes[child["id"]], nodes[grandchild["id"]]

    assert moved["parent_id"] == b["id"]
    assert moved["path"] == f"{b['path']}{child['id']}/"
    assert moved["depth"] == 2
    # The whole subtree must follow, not just the node that was dragged.
    assert moved_gc["path"] == f"{moved['path']}{grandchild['id']}/"
    assert moved_gc["depth"] == 3


def test_cannot_move_node_into_its_own_descendant(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    parent = _add(client, project["id"], root["id"], "Parent")
    child = _add(client, project["id"], parent["id"], "Child")

    r = client.post(f"/api/nodes/{parent['id']}/move", json={"new_parent_id": child["id"]})
    assert r.status_code == 400
    assert "descendant" in r.json()["detail"].lower()

    r = client.post(f"/api/nodes/{parent['id']}/move", json={"new_parent_id": parent["id"]})
    assert r.status_code == 400


def test_subtree_prefix_does_not_match_sibling_with_shared_digits(client, project):
    """'/1/7/%' must not match '/1/70/'. The trailing slash is what saves us."""
    root = _tree(client, project["id"])["nodes"][0]
    nodes = [_add(client, project["id"], root["id"], f"N{i}") for i in range(12)]
    target = nodes[0]
    r = client.get(f"/api/nodes/{target['id']}")
    assert r.json()["descendant_count"] == 0


def test_delete_removes_whole_subtree(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    branch = _add(client, project["id"], root["id"], "Doomed")
    _add(client, project["id"], branch["id"], "Doomed Child")
    kid2 = _add(client, project["id"], branch["id"], "Doomed Child 2")
    _add(client, project["id"], kid2["id"], "Doomed Grandchild")

    r = client.delete(f"/api/nodes/{branch['id']}")
    assert r.status_code == 200
    assert r.json()["deleted_count"] == 4
    assert client.get(f"/api/nodes/{kid2['id']}").status_code == 404


# --- tags --------------------------------------------------------------------

def test_cascading_tag_applies_to_descendants(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    branch = _add(client, project["id"], root["id"], "Electrical Branch")
    child = _add(client, project["id"], branch["id"], "Harness")
    grandchild = _add(client, project["id"], child["id"], "Connector")

    tag = client.post("/api/tags", json={"name": "TestElectrical", "color": "#3b82f6"}).json()
    r = client.post(f"/api/nodes/{branch['id']}/tags", json={"tag_id": tag["id"], "cascade": True})
    assert r.status_code == 201

    tags_by_node = _tree(client, project["id"])["tags_by_node"]
    gc_tags = tags_by_node[str(grandchild["id"])]
    entry = [t for t in gc_tags if t["tag_id"] == tag["id"]][0]
    assert entry["inherited"] is True
    assert entry["source_node_id"] == branch["id"]

    # The node it was applied to owns it directly, not by inheritance.
    own = [t for t in tags_by_node[str(branch["id"])] if t["tag_id"] == tag["id"]][0]
    assert own["inherited"] is False


def test_node_added_later_inherits_existing_branch_tag(client, project):
    """The reason cascade is resolved at read time instead of copied on write."""
    root = _tree(client, project["id"])["nodes"][0]
    branch = _add(client, project["id"], root["id"], "Late Branch")
    tag = client.post("/api/tags", json={"name": "LateTag"}).json()
    client.post(f"/api/nodes/{branch['id']}/tags", json={"tag_id": tag["id"], "cascade": True})

    latecomer = _add(client, project["id"], branch["id"], "Added Afterwards")
    detail = client.get(f"/api/nodes/{latecomer['id']}").json()
    assert any(t["tag_id"] == tag["id"] and t["inherited"] for t in detail["tags"])


def test_non_cascading_tag_stays_put(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    branch = _add(client, project["id"], root["id"], "Solo Branch")
    child = _add(client, project["id"], branch["id"], "Solo Child")
    tag = client.post("/api/tags", json={"name": "SoloTag"}).json()
    client.post(f"/api/nodes/{branch['id']}/tags", json={"tag_id": tag["id"], "cascade": False})

    detail = client.get(f"/api/nodes/{child['id']}").json()
    assert not any(t["tag_id"] == tag["id"] for t in detail["tags"])


def test_removing_inherited_tag_points_at_the_source(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    branch = _add(client, project["id"], root["id"], "Src Branch")
    child = _add(client, project["id"], branch["id"], "Src Child")
    tag = client.post("/api/tags", json={"name": "SrcTag"}).json()
    client.post(f"/api/nodes/{branch['id']}/tags", json={"tag_id": tag["id"], "cascade": True})

    r = client.delete(f"/api/nodes/{child['id']}/tags/{tag['id']}")
    assert r.status_code == 409
    assert str(branch["id"]) in r.json()["detail"]


def test_reassigning_a_tag_toggles_cascade_idempotently(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    branch = _add(client, project["id"], root["id"], "Toggle Branch")
    child = _add(client, project["id"], branch["id"], "Toggle Child")
    tag = client.post("/api/tags", json={"name": "ToggleTag"}).json()

    client.post(f"/api/nodes/{branch['id']}/tags", json={"tag_id": tag["id"], "cascade": False})
    r = client.post(f"/api/nodes/{branch['id']}/tags", json={"tag_id": tag["id"], "cascade": True})
    assert r.status_code == 201

    detail = client.get(f"/api/nodes/{child['id']}").json()
    assert any(t["tag_id"] == tag["id"] for t in detail["tags"])


# --- filtering ---------------------------------------------------------------

def test_filter_returns_ancestors_so_the_tree_can_render(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    lvl1 = _add(client, project["id"], root["id"], "Level 1")
    lvl2 = _add(client, project["id"], lvl1["id"], "Level 2")
    target = _add(client, project["id"], lvl2["id"], "Deep Target", status="needs_rework")

    r = client.get(f"/api/projects/{project['id']}/filter", params={"status": ["needs_rework"]})
    assert r.status_code == 200
    data = r.json()

    assert target["id"] in data["matched_ids"]
    # Only the deep node matched, but every ancestor must be visible or the row
    # has nothing to hang off in the UI.
    for ancestor in (root["id"], lvl1["id"], lvl2["id"]):
        assert ancestor in data["visible_ids"]
        assert ancestor not in data["matched_ids"]


def test_filter_tag_mode_all_vs_any(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    both = _add(client, project["id"], root["id"], "Has Both")
    one = _add(client, project["id"], root["id"], "Has One")

    t1 = client.post("/api/tags", json={"name": "FilterA"}).json()
    t2 = client.post("/api/tags", json={"name": "FilterB"}).json()
    client.post(f"/api/nodes/{both['id']}/tags", json={"tag_id": t1["id"]})
    client.post(f"/api/nodes/{both['id']}/tags", json={"tag_id": t2["id"]})
    client.post(f"/api/nodes/{one['id']}/tags", json={"tag_id": t1["id"]})

    params = {"tags": ["filtera", "filterb"]}
    any_ids = client.get(
        f"/api/projects/{project['id']}/filter", params={**params, "tag_mode": "any"}
    ).json()["matched_ids"]
    all_ids = client.get(
        f"/api/projects/{project['id']}/filter", params={**params, "tag_mode": "all"}
    ).json()["matched_ids"]

    assert {both["id"], one["id"]}.issubset(set(any_ids))
    assert both["id"] in all_ids and one["id"] not in all_ids


def test_filter_by_text_searches_part_number(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    node = _add(client, project["id"], root["id"], "Mystery Bracket", part_number="ZZZ-9910")
    r = client.get(f"/api/projects/{project['id']}/filter", params={"q": "zzz-99"})
    assert node["id"] in r.json()["matched_ids"]


# --- cloning -----------------------------------------------------------------

def test_clone_project_deep_copies_tree_and_tags(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    branch = _add(client, project["id"], root["id"], "Cloneable", status="installed")
    _add(client, project["id"], branch["id"], "Cloneable Child", status="installed")
    tag = client.post("/api/tags", json={"name": "CloneTag"}).json()
    client.post(f"/api/nodes/{branch['id']}/tags", json={"tag_id": tag["id"], "cascade": True})

    r = client.post(
        "/api/projects/clone",
        json={"name": "Next Year Car", "source_project_id": project["id"], "reset_status": "concept"},
    )
    assert r.status_code == 201, r.text
    clone = r.json()

    original = _tree(client, project["id"])
    copied = _tree(client, clone["id"])
    assert len(copied["nodes"]) == len(original["nodes"])
    assert {n["name"] for n in copied["nodes"]} >= {"Cloneable", "Cloneable Child"}

    # Statuses reset, so nothing arrives pre-marked as built.
    assert all(n["status"] == "concept" for n in copied["nodes"])
    # Fresh ids and fresh paths -- no leakage from the source project.
    assert not (
        {n["id"] for n in copied["nodes"]} & {n["id"] for n in original["nodes"]}
    )
    copied_branch = [n for n in copied["nodes"] if n["name"] == "Cloneable"][0]
    child = [n for n in copied["nodes"] if n["name"] == "Cloneable Child"][0]
    assert child["path"].startswith(copied_branch["path"])
    # And the cascading tag came along.
    assert any(
        t["tag_id"] == tag["id"]
        for t in copied["tags_by_node"].get(str(child["id"]), [])
    )


def test_duplicate_node_copies_subtree_in_place(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    corner = _add(client, project["id"], root["id"], "Upright Assembly")
    _add(client, project["id"], corner["id"], "Bearing")
    _add(client, project["id"], corner["id"], "Spacer")

    r = client.post(f"/api/nodes/{corner['id']}/duplicate", json={"name": "Upright Assembly RH"})
    assert r.status_code == 201, r.text
    dupe = r.json()
    assert dupe["name"] == "Upright Assembly RH"
    assert dupe["descendant_count"] == 2
    assert dupe["parent_id"] == root["id"]


# --- files -------------------------------------------------------------------

def test_upload_download_and_versioning(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    node = _add(client, project["id"], root["id"], "Bracket")

    r = client.post(
        "/api/attachments",
        data={"node_id": node["id"], "notes": "first revision"},
        files={"file": ("bracket.step", b"ISO-10303-21; v1", "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    v1 = r.json()
    assert v1["version"] == 1 and v1["is_current"] is True
    assert v1["kind"] == "cad"  # inferred from the .step extension

    r = client.post(
        "/api/attachments",
        data={"node_id": node["id"]},
        files={"file": ("bracket.step", b"ISO-10303-21; v2 revised", "application/octet-stream")},
    )
    v2 = r.json()
    assert v2["version"] == 2

    current = client.get("/api/attachments", params={"node_id": node["id"]}).json()
    assert [a["id"] for a in current] == [v2["id"]]  # v1 demoted, not deleted

    all_versions = client.get(
        "/api/attachments", params={"node_id": node["id"], "include_old_versions": True}
    ).json()
    assert len(all_versions) == 2

    dl = client.get(f"/api/attachments/{v1['id']}/download")
    assert dl.status_code == 200
    assert dl.content == b"ISO-10303-21; v1"
    assert "attachment" in dl.headers["content-disposition"]


def test_identical_files_are_stored_once(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    a = _add(client, project["id"], root["id"], "Part A")
    b = _add(client, project["id"], root["id"], "Part B")
    payload = b"same bytes for both parts"

    r1 = client.post(
        "/api/attachments", data={"node_id": a["id"]},
        files={"file": ("shared.pdf", payload, "application/pdf")},
    ).json()
    r2 = client.post(
        "/api/attachments", data={"node_id": b["id"]},
        files={"file": ("shared.pdf", payload, "application/pdf")},
    ).json()

    assert r1["sha256"] == r2["sha256"]
    from app import storage
    assert storage.blob_path(r1["sha256"]).exists()

    # Deleting one must NOT pull the bytes out from under the other.
    assert client.delete(f"/api/attachments/{r1['id']}").status_code == 204
    assert storage.blob_path(r2["sha256"]).exists()
    assert client.get(f"/api/attachments/{r2['id']}/download").content == payload


def test_directory_traversal_filename_is_neutralized(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    node = _add(client, project["id"], root["id"], "Sketchy")
    r = client.post(
        "/api/attachments", data={"node_id": node["id"]},
        files={"file": ("../../../../etc/passwd", b"nope", "text/plain")},
    )
    assert r.status_code == 201
    assert "/" not in r.json()["filename"] and "\\" not in r.json()["filename"]
    assert not r.json()["filename"].startswith(".")


def test_blocked_extension_is_refused(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    node = _add(client, project["id"], root["id"], "No Executables")
    r = client.post(
        "/api/attachments", data={"node_id": node["id"]},
        files={"file": ("virus.exe", b"MZ", "application/octet-stream")},
    )
    assert r.status_code == 415


def test_deleting_node_deletes_its_attachment_rows(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    node = _add(client, project["id"], root["id"], "Ephemeral")
    att = client.post(
        "/api/attachments", data={"node_id": node["id"]},
        files={"file": ("doomed.txt", b"bye", "text/plain")},
    ).json()

    client.delete(f"/api/nodes/{node['id']}")
    assert client.get(f"/api/attachments/{att['id']}/download").status_code == 404


# --- metadata & export -------------------------------------------------------

def test_patch_updates_only_supplied_fields(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    node = _add(
        client, project["id"], root["id"], "Metadata Part",
        part_number="ABC-1", material="6061", vendor="McMaster",
    )
    r = client.patch(f"/api/nodes/{node['id']}", json={"status": "ordered"})
    assert r.status_code == 200
    updated = r.json()
    assert updated["status"] == "ordered"
    assert updated["material"] == "6061"     # untouched
    assert updated["part_number"] == "ABC-1"


def test_invalid_status_is_rejected(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    r = client.post(
        "/api/nodes",
        json={"project_id": project["id"], "parent_id": root["id"], "name": "Bad", "status": "wat"},
    )
    assert r.status_code == 422


def test_rollup_sums_cost_over_subtree(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    asm = _add(client, project["id"], root["id"], "Cost Assembly")
    _add(client, project["id"], asm["id"], "Cheap", cost_cents=100, quantity=2)
    _add(client, project["id"], asm["id"], "Pricey", cost_cents=5000, quantity=1)

    detail = client.get(f"/api/nodes/{asm['id']}").json()
    assert detail["rollup_cost_cents"] == 100 * 2 + 5000


def test_csv_export_has_a_row_per_node(client, project):
    root = _tree(client, project["id"])["nodes"][0]
    _add(client, project["id"], root["id"], "Exported Part", part_number="EXP-1")
    r = client.get(f"/api/projects/{project['id']}/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "EXP-1" in r.text
    body_rows = [ln for ln in r.text.strip().splitlines()[1:] if ln.strip()]
    assert len(body_rows) == len(_tree(client, project["id"])["nodes"])
