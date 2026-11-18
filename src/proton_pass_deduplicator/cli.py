import typer
from pathlib import Path
from .data import ProtonPassExport
from rich import print as rprint
from typing import Annotated

app = typer.Typer()


@app.command()
def inspect(filepath: str):
    filepath = Path(filepath)
    export = ProtonPassExport(filepath)
    vault_number = len(export.vaults)
    rprint(
        f"Passes are separated into {vault_number} vaults: {list(export.vaults.keys())}"
    )
    rprint(f"There are {len(export)} passes in total.")


@app.command()
def deduplicate(
    file: Annotated[
        str,
        typer.Argument(
            help="Path to ZIP archive containing passes exported from Proton Pass"
        ),
    ],
    output: str = None,
    main_vault: Annotated[
        str, typer.Option(help="First occurences in this vault are retained.")
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            help="Only show the results of deduplication.", show_default=False
        ),
    ] = False,
):
    if not dry_run:
        if output is None:
            output = typer.prompt("Please, provide the path for output file")
        if main_vault is None:
            default_vault = typer.confirm(
                "Are you sure you want to use the first vault as a main vault"
            )
            if not default_vault:
                main_vault = typer.prompt("Please, provide the name of main vault")

    filepath = Path(file)
    export = ProtonPassExport(filepath)
    unique_passes, unique_files = export.get_unique()
    rprint(f"There are {len(unique_passes)} unique of {len(export)} passes in total.")
    rprint(
        f"There are {len(unique_files)} unique files corresponding to unique passes."
    )

    if dry_run:
        raise typer.Exit(0)

    export.deduplicate(unique_passes, unique_files)
    export.save(output)
    rprint(f"Deduplicated passes were successfuly exported to: {output}.")
    rprint("Check out the instruction on [link=https://proton.me/support/pass-export#import]How to import passes into Proton Pass[/link]")


if __name__ == "__main__":
    app()
