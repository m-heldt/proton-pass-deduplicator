import typer
from pathlib import Path
from .data import ProtonPassExport
from rich import print as rprint

app = typer.Typer()

@app.command()
def inspect(filepath: str):
    filepath = Path(filepath)
    export = ProtonPassExport(filepath)
    vault_number = len(export.vaults)
    rprint(f"Passes are separated into {vault_number} vaults: {list(export.vaults.keys())}")
    rprint(f"There are {len(export)} passes in total.")

@app.command()
def deduplicate(filepath: str, dry_run: bool = typer.Option(True, "--dry-run")):
    filepath = Path(filepath)
    export = ProtonPassExport(filepath)
    unique_passes = export.get_unique()
    rprint(f"There are {len(unique_passes)} of {len(export)} in total.")


if __name__ == "__main__":
    app()