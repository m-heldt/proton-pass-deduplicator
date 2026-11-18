from pathlib import Path
import zipfile
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Self, Any
from pydantic import BaseModel, Field
import hashlib
from functools import cached_property
import zipremove
from rich import print as rprint
import os


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
    DATA_JSON_PATH = "Proton Pass/data.json"
    FILES_PATH = "Proton Pass/files"

    def __init__(self, path: Path | str):
        if not Path(path).exists():
            raise FileNotFoundError("The file does not exist")

        self.path = Path(path)
        self._data = {}
        self._files = []
        self._files_to_remove = []
        self._load()
        self.main_vault = None

    def _load(self) -> None:
        with zipfile.ZipFile(self.path) as archive:
            self._data = json.load(archive.open(self.DATA_JSON_PATH))
            files = archive.namelist()
            attachments = [Path(file).name for file in files if Path(file).parent == Path(self.FILES_PATH)]
            self._files = attachments

    @property
    def vaults(self):
        return {
            self._data["vaults"][id]["name"]: Vault(
                id=id,
                name=self._data["vaults"][id]["name"],
                items=self._data["vaults"][id]["items"],
            )
            for id in self._data["vaults"]
        }

    def get_unique(self) -> set:
        if self.main_vault is None:
            first_vault = list(self.vaults.values())[0]
            main_vault = first_vault
        else:
            main_vault = self.vaults[self.main_vault]
        vaults = [main_vault]
        for vault in self.vaults.values():
            if vault not in vaults:
                vaults.append(vault)

        seen_hashes = set()
        items_unique = set()
        files = []
        for vault in vaults:
            for item in vault.items:
                if item.hash not in seen_hashes:
                    seen_hashes.add(item.hash)
                    items_unique.add(item.itemId)
                    if item.files:
                        files.extend(item.files)

        files_unique = set(files)

        return items_unique, files_unique

    def deduplicate(self, items_unique, files_unique):
        for vault in self._data["vaults"].values():
            vault["items"][:] = [
                item for item in vault["items"] if item["itemId"] in items_unique
            ]
        self._files_to_remove = [file for file in self._files if file not in files_unique]
        self._files = list(files_unique)

    @property
    def main_vault(self):
        return self._main_vault

    @main_vault.setter
    def main_vault(self, value: str | None) -> None:
        if value is not None and value not in self.vaults:
            raise ValueError("Such vault does not exist")
        self._main_vault = value

    def __len__(self) -> int:
        size = 0
        for vault in self.vaults.values():
            size += len(vault.items)
        return size

    def save(self, path: Path | str):
        path = Path(path)
        if path.exists():
            raise FileExistsError("The file exists")
        self.path.copy(path)

        with zipremove.ZipFile(path, "a") as archive:
            info_on_json = archive.getinfo(self.DATA_JSON_PATH)

            if self._files_to_remove:
                removed = [archive.remove(os.path.join(self.FILES_PATH, file)) for file in self._files_to_remove]
                archive.repack(removed)

            removed = archive.remove(self.DATA_JSON_PATH)
            archive.repack([removed])

            archive.writestr(
                self.DATA_JSON_PATH,
                json.dumps(self._data),
                compress_type=info_on_json.compress_type,
            )
