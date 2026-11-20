import json
from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import pytest

from proton_pass_deduplicator.data import PassItem, PassItemData, ProtonPassExport

DATA_PATH = "Proton Pass/data.json"
FILES_PATH = "Proton Pass/files"
README_PATH = "Proton Pass/README.txt"


def make_item(
    item_id: str,
    *,
    email: str = "test@example.com",
    files: tuple[str, ...] = (),
) -> dict:
    return {
        "itemId": item_id,
        "shareId": "share-1",
        "folderId": "folder-1",
        "data": {
            "metadata": {"itemUuid": f"uuid-{item_id}", "name": "Test login", "note": ""},
            "extraFields": [],
            "type": "login",
            "content": {"itemEmail": email, "itemUsername": "test-user"},
        },
        "state": 1,
        "aliasEmail": None,
        "contentFormatVersion": 1,
        "createTime": 100,
        "modifyTime": 200,
        "pinned": False,
        "shareCount": 0,
        "files": list(files),
    }


@pytest.fixture
def export_document() -> dict:
    return {
        "version": 1,
        "vaults": {
            "personal-id": {
                "name": "Personal",
                "items": [
                    make_item("first", files=("first.txt", "shared.txt")),
                    make_item("same-vault-copy", files=("same-vault-copy.txt", "shared.txt")),
                    make_item("other", email="other@example.com", files=("shared.txt",)),
                ],
            },
            "work-id": {
                "name": "Work",
                "items": [
                    make_item("work-copy", files=("work-copy.txt", "shared.txt")),
                    make_item("work-only", email="work@example.com"),
                ],
            },
        },
    }


@pytest.fixture
def export_path(tmp_path: Path, export_document: dict) -> Path:
    path = tmp_path / "export.zip"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(DATA_PATH, json.dumps(export_document))
        for filename in ("first.txt", "same-vault-copy.txt", "work-copy.txt"):
            archive.writestr(f"{FILES_PATH}/{filename}", b"synthetic attachment")
        archive.writestr(f"{FILES_PATH}/shared.txt", b"shared attachment")
        archive.writestr(README_PATH, b"extra archive member")
    return path


def test_pass_item_data_removes_uuid_and_preserves_other_metadata():
    metadata = {"itemUuid": "uuid-test", "name": "Test", "note": "Note"}
    content = {"itemEmail": "test@example.com"}

    item = PassItemData(metadata=metadata, extraFields=[], type="login", content=content)

    assert item.metadata == {"name": "Test", "note": "Note"}
    assert item.content == content
    assert metadata["itemUuid"] == "uuid-test"


def test_pass_item_from_item_parses_nested_data_and_defaults_to_no_files():
    raw_item = make_item("first")
    del raw_item["files"]

    item = PassItem.from_item(raw_item)

    assert item.itemId == "first"
    assert isinstance(item.data, PassItemData)
    assert item.data.metadata == {"name": "Test login", "note": ""}
    assert item.files == []


def test_item_hash_matches_copies_with_different_ids_and_json_key_order():
    original = make_item("original")
    copy = make_item("copy")
    copy["shareId"] = "another-share"
    copy["data"]["content"] = {"itemUsername": "test-user", "itemEmail": "test@example.com"}

    assert PassItem.from_item(original).hash == PassItem.from_item(copy).hash


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        pytest.param(("createTime",), 101, id="creation-time"),
        pytest.param(("data", "type"), "note", id="item-type"),
        pytest.param(("data", "metadata", "note"), "Different note", id="metadata"),
        pytest.param(("data", "content", "itemEmail"), "other@example.com", id="login-content"),
        pytest.param(("data", "extraFields"), [{"fieldName": "Account"}], id="custom-fields"),
    ],
)
def test_item_hash_differs_when_matching_fields_change(field_path, value):
    original = make_item("original")
    changed = deepcopy(original)
    parent = changed
    for field in field_path[:-1]:
        parent = parent[field]
    parent[field_path[-1]] = value

    assert PassItem.from_item(original).hash != PassItem.from_item(changed).hash


def test_export_loads_vaults_and_counts_items_from_a_string_path(export_path):
    export = ProtonPassExport(str(export_path))

    assert set(export.vaults) == {"Personal", "Work"}
    assert export.vaults["Personal"].id == "personal-id"
    assert [item.itemId for item in export.vaults["Work"].items] == ["work-copy", "work-only"]
    assert len(export) == 5


def test_export_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        ProtonPassExport(tmp_path / "missing.zip")


def test_export_rejects_non_zip_file(tmp_path):
    path = tmp_path / "export.zip"
    path.write_text("invalid ZIP", encoding="utf-8")

    with pytest.raises(BadZipFile):
        ProtonPassExport(path)


def test_export_rejects_zip_without_data_json(tmp_path):
    path = tmp_path / "export.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr(README_PATH, "no data in this archive")

    with pytest.raises(KeyError, match=DATA_PATH):
        ProtonPassExport(path)


def test_export_rejects_invalid_json(tmp_path):
    path = tmp_path / "export.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr(DATA_PATH, "{")

    with pytest.raises(json.JSONDecodeError):
        ProtonPassExport(path)


@pytest.mark.parametrize(
    ("main_vault", "retained_id", "retained_file"),
    [
        pytest.param(None, "first", "first.txt", id="default-vault"),
        pytest.param("Work", "work-copy", "work-copy.txt", id="preferred-vault"),
    ],
)
def test_get_unique_keeps_first_match_in_vault_order(
    export_path, main_vault, retained_id, retained_file
):
    export = ProtonPassExport(export_path)
    export.main_vault = main_vault

    item_ids, filenames = export.get_unique()

    assert item_ids == {retained_id, "other", "work-only"}
    assert filenames == {retained_file, "shared.txt"}
    assert len(export) == 5


def test_clearing_main_vault_restores_default_order(export_path):
    export = ProtonPassExport(export_path)
    export.main_vault = "Work"

    export.main_vault = None

    assert export.main_vault is None
    assert export.get_unique()[0] == {"first", "other", "work-only"}


def test_unknown_main_vault_leaves_existing_selection_in_place(export_path):
    export = ProtonPassExport(export_path)
    export.main_vault = "Work"

    with pytest.raises(ValueError):
        export.main_vault = "Missing"

    assert export.main_vault == "Work"


def test_get_unique_returns_empty_sets_for_empty_vault(tmp_path):
    path = tmp_path / "empty.zip"
    document = {"vaults": {"empty-id": {"name": "Empty", "items": []}}}
    with ZipFile(path, "w") as archive:
        archive.writestr(DATA_PATH, json.dumps(document))

    export = ProtonPassExport(path)

    assert len(export) == 0
    assert export.get_unique() == (set(), set())


def test_deduplicate_filters_items_and_preserves_order_within_each_vault(export_path):
    export = ProtonPassExport(export_path)
    export.main_vault = "Work"

    export.deduplicate(*export.get_unique())

    assert len(export) == 3
    assert [item.itemId for item in export.vaults["Personal"].items] == ["other"]
    assert [item.itemId for item in export.vaults["Work"].items] == ["work-copy", "work-only"]
    assert export.get_unique() == (
        {"other", "work-copy", "work-only"},
        {"shared.txt", "work-copy.txt"},
    )


def test_save_after_deduplication_preserves_raw_records_and_retained_files(
    export_path, export_document, tmp_path
):
    source_bytes = export_path.read_bytes()
    output_path = tmp_path / "deduplicated.zip"
    export = ProtonPassExport(export_path)
    export.deduplicate(*export.get_unique())

    export.save(output_path)

    expected_document = deepcopy(export_document)
    del expected_document["vaults"]["personal-id"]["items"][1]
    del expected_document["vaults"]["work-id"]["items"][0]
    expected_members = [DATA_PATH, f"{FILES_PATH}/first.txt", f"{FILES_PATH}/shared.txt", README_PATH]
    with ZipFile(output_path) as archive:
        assert sorted(archive.namelist()) == sorted(expected_members)
        assert json.loads(archive.read(DATA_PATH)) == expected_document
        assert archive.getinfo(DATA_PATH).compress_type == ZIP_DEFLATED
        assert archive.read(f"{FILES_PATH}/first.txt") == b"synthetic attachment"
        assert archive.read(f"{FILES_PATH}/shared.txt") == b"shared attachment"
        assert archive.read(README_PATH) == b"extra archive member"
    assert export_path.read_bytes() == source_bytes


def test_save_without_deduplication_preserves_all_archive_members(export_path, tmp_path):
    output_path = tmp_path / "copy.zip"

    ProtonPassExport(export_path).save(str(output_path))

    with ZipFile(export_path) as source, ZipFile(output_path) as result:
        assert sorted(result.namelist()) == sorted(source.namelist())
        assert json.loads(result.read(DATA_PATH)) == json.loads(source.read(DATA_PATH))
        for member in source.namelist():
            if member != DATA_PATH:
                assert result.read(member) == source.read(member)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="Reapplying deduplication clears pending attachment removals.",
)
def test_saving_after_reapplying_deduplication_still_removes_duplicate_attachments(
    export_path, tmp_path
):
    export = ProtonPassExport(export_path)
    selection = export.get_unique()
    output_path = tmp_path / "deduplicated.zip"

    export.deduplicate(*selection)
    export.deduplicate(*selection)
    export.save(output_path)

    with ZipFile(output_path) as archive:
        assert set(archive.namelist()) == {
            DATA_PATH,
            f"{FILES_PATH}/first.txt",
            f"{FILES_PATH}/shared.txt",
            README_PATH,
        }


def test_save_rejects_existing_destination_and_preserves_its_bytes(export_path, tmp_path):
    output_path = tmp_path / "existing.zip"
    output_path.write_bytes(b"existing file")

    with pytest.raises(FileExistsError):
        ProtonPassExport(export_path).save(output_path)

    assert output_path.read_bytes() == b"existing file"
