from pathlib import Path
import zipfile
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Self, Any
from pydantic import BaseModel, Field
import hashlib
from functools import cached_property


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
    duplicate: bool = Field(False, repr=False)

    @cached_property
    def hash(self):
        model = self.data.model_dump()
        model["createTime"] = self.createTime
        return hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_item(cls, item: dict) -> Self:
        return cls(**item)


class Vault(BaseModel):
    id: str
    name: str
    items: list[PassItem] = Field(repr=False)



class ProtonPassExport:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._data = {}
        self._load()
        self.main_vault = None

    def _load(self) -> None:
        DATA_JSON_PATH = "Proton Pass/data.json"

        with zipfile.ZipFile(self.path) as archive:
            self._data = json.load(archive.open(DATA_JSON_PATH))

    @cached_property
    def vaults(self) -> list:
        return {
            self._data["vaults"]["name"]: Vault(
                id=id,
                name=self._data["vaults"][id]["name"],
                items=self._data["vaults"][id]["items"],
            )
            for id in self._data["vaults"]
        }


    def mark_duplicates(self, main_vault_name: str):
        main_vault = self.vaults[main_vault_name]
        vaults = [main_vault]
        for vault in self.vaults:
            if vault not in vaults:
                vaults.append(vault)

        items_deduplicated = {}
        for vault in vaults:
            for item in vault:
                if item.hash not in items_deduplicated:
                    items_deduplicated[item.hash]

    @main_vault.setter
    def main_vault(self, value: str | None) -> None:
        if value is not None and value in self.vaults.keys():
            self.main_vault = value
