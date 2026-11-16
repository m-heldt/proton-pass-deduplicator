from pathlib import Path
import zipfile
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Self, Any
from pydantic import BaseModel, Field
import hashlib



class PassItemDataContent(BaseModel):
    itemEmail: str
    password: str
    totpUri: str
    passkeys: list[Any]
    itemUsername: str
    autofillUrls: list[Any]
    urls: list[Any]


class PassItemData(BaseModel):
    metadata: dict
    extraFields: list[Any]
    type: str
    content: dict

    def model_post_init(self, _context):
        self.metadata.pop("itemUuid")


class PassItem(BaseModel):
    itemId: str
    shareId: str
    data: PassItemData | None = None
    state: int | None
    aliasEmail: int | None
    contentFormatVersion: int
    createTime: int | None
    modifyTime: int | None
    pinned: bool
    shareCount: int
    files: list[str] = Field(default_factory=list)

    @property
    def hash(self):
        model = self.data.model_dump()
        model["createTime"] = self.createTime
        return hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_item(cls, item: dict) -> Self:
        return cls(**item)


class VaultItems(BaseModel):
    id: str
    name: str
    items: list[PassItem]



class ProtonPassExport:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._data = {}
        self._load()

    def _load(self) -> None:
        DATA_JSON_PATH = "Proton Pass/data.json"
        
        with zipfile.ZipFile(self.path) as archive:
            self._data = json.load(archive.open(DATA_JSON_PATH))

    @property
    def vaults(self) -> list:
        return [VaultItems(id=id, name=self._data["vaults"][id]["name"], items=self.get_items(id)) for id in self._data["vaults"]]

    def get_vault_list(self) -> list:
        return list(self._data["vaults"].keys())

    def get_items_copy(self, vault_id: str) -> list[Any]:
        items_copy = deepcopy(self._data["vaults"][vault_id]["items"])
        return items_copy

    def get_items(self, vault_id: str) -> list[PassItem]:
        return [PassItem(**item) for item in self._data["vaults"][vault_id]["items"]]