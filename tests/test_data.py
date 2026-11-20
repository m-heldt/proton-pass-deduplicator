import pytest
import proton_pass_deduplicator.data as data


def test_pass_item_data_removes_uuid_preserves_other():
    
    metadata = {
            "itemUuid": 42,
            "name": "Test",
            "note": "Note"
        }
    pass_item_data = data.PassItemData(
        metadata=metadata,
        extraFields=[],
        type="type",
        content={
            "itemEmail": "m@h.com"
        }
    )

    assert "itemUuid" not in pass_item_data.metadata
    assert pass_item_data.metadata["name"] == "Test"
    assert pass_item_data.metadata["note"] == "Note"


@pytest.mark.parametrize("path,unique_items,unique_files", [
    ("./artifacts/Proton Pass_export_2026-11-10_1794325477.zip", 2044, 17),
    ("./artifacts/Proton Pass_export_2026-11-18_1794961771.zip", 2047, 17)
])
def test_get_unique(path, unique_items, unique_files):
    export = data.ProtonPassExport(path)
    u_items, u_files = export.get_unique()
    assert len(u_items) == unique_items
    assert len(u_files) == unique_files