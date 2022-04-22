import logging
import sys
from typing import Iterable, ClassVar, List
from collections import defaultdict

import tabulate
import lxml.etree as ET
import click
import tqdm

from chocomufin.funcs import Translator, check_file, get_hex, convert_file, update_table, get_character_name,\
    normalize
from chocomufin.parsers import Parser, Alto, PlainText
logging.getLogger().setLevel(logging.INFO)


PARSERS = click.Choice(["alto", "txt"])


def _get_unorm(ctx):
    return ctx.obj.get("unorm")


def _get_parser(parser_choice: str) -> ClassVar[Parser]:
    if parser_choice == "alto":
        return Alto
    elif parser_choice == "txt":
        return PlainText
    raise ValueError("Unknown parser")


@click.group()
@click.option("--debug", default=False, is_flag=True, show_default=True)
@click.option("-n", "--norm", default=None, help="Unicode normalization to apply", show_default=True)
@click.pass_context
def main(ctx: click.Context, debug: bool = False, norm: str = "NFC"):
    """Mufi checkers allow for multiple things"""
    if debug:
        logging.getLogger().setLevel(logging.INFO)
    else:
        logging.getLogger().setLevel(logging.WARNING)
    ctx.obj = {"unorm": norm}


@main.command("control")
@click.argument("table", type=click.Path(exists=True, file_okay=True, dir_okay=False))
@click.argument("files", type=click.Path(exists=True, file_okay=True, dir_okay=False), nargs=-1)
@click.option("-s", "--ignore", type=click.STRING, default=".mufichecker.xml", show_default=True)
@click.option("--parser", type=PARSERS, default="alto", help="XML format of the file", show_default=True)
@click.pass_context
def control(ctx: click.Context, table: str, files: Iterable[str], ignore: str, parser: str = "alto"):
    control_table = Translator.parse(
        table,
        normalization_method=_get_unorm(ctx)
    )
    errors = defaultdict(list)
    missing_chars = set()
    parser = _get_parser(parser)

    for file in tqdm.tqdm(files):
        if ignore in file:  # Skip converted content
            continue
        new_chars = check_file(
            file,
            translator=control_table,
            normalization_method=_get_unorm(ctx),
            parser=parser
        )
        if new_chars:
            for char in new_chars:
                errors[char].append(file)
            missing_chars = missing_chars.union(new_chars)

    # Generate the controlling table
    table = [["Character", "Hex-representation", "Name", "Files"]]
    for char in errors:
        table.append([
            char.strip(),
            get_hex(char),
            get_character_name(char, raise_exception=False),
            errors[char][0]
        ])
        if len(errors[char]) > 1:
            for file in errors[char][1:]:
                table.append(["", "", "", file])

    # Prints table and exits
    if len(table) > 1:
        click.echo(
            click.style(f"ERROR : {len(errors)} characters found that were not in the conversion table", fg='red'),
            color=True
        )
        click.echo("----\nREPORT\n----")
        print(tabulate.tabulate(table, headers="firstrow", tablefmt="fancy_grid"))
        sys.exit(1)
    else:
        click.echo(
            click.style("No new characters found", fg="green")
        )
        sys.exit(0)


@main.command("convert")
@click.argument("table", type=click.Path(file_okay=True, dir_okay=False))
@click.argument("files", type=click.Path(exists=True, file_okay=True, dir_okay=False), nargs=-1)
@click.option("-s", "--suffix", type=click.STRING, default=".mufichecker.xml", show_default=True)
@click.option("--parser", type=PARSERS, default="alto", help="XML format of the file", show_default=True)
@click.pass_context
def convert(
        ctx: click.Context,
        table: str,
        files: Iterable[str],
        suffix: str = ".mufichecker.xml",
        parser: str = "alto"):
    """ Given a conversion TABLE generated by the `generate` command, normalizes FILES and saves the output
    in file with SUFFIX."""
    control_table = Translator.parse(
        table,
        normalization_method=_get_unorm(ctx)
    )
    parser = _get_parser(parser)

    for file in tqdm.tqdm(files):
        if suffix in file:  # Skip converted content
            continue

        instance: Parser = convert_file(file, control_table, normalization_method=_get_unorm(ctx), parser=parser)
        with open(file.replace(".xml", suffix) if ".xml" in file else file+suffix, "w") as f:
            f.write(instance.dump())


@main.command("generate")
@click.argument("table", type=click.Path(file_okay=True, dir_okay=False))
@click.argument("files", type=click.Path(exists=True, file_okay=True, dir_okay=False), nargs=-1)
@click.option("--mode", type=click.Choice(["keep", "reset", "cleanup"]),
              default="keep", help="Mode used to take into account the original [TABLE] if it exists. "
                                   "--mode=keep keeps the original data, even if they are not in the [FILES],"
                                   " --mode=reset will drop everything from the original table,"
                                   " --mode=cleanup will drop values which have not been found in the [FILES].",
              show_default=True)
@click.option("--parser", type=click.Choice(["alto"]), default="alto", help="XML format of the file", show_default=True)
@click.option("--dest", type=click.Path(file_okay=True, dir_okay=False), default=None,
              help="If set up, instead of writing to file in update, will write in dest")
@click.pass_context
def generate(ctx: click.Context, table: str, files: Iterable[str], mode: str = "keep", parser: str = "alto",
             dest: str = None):
    """ Generate a [TABLE] of accepted character for transcriptions based on [FILES]
    """
    parser = _get_parser(parser)
    update_table(
        files=files,
        table_file=table,
        echo=True,
        dest=dest,
        mode=mode,
        parser=parser,
        normalization_method=_get_unorm(ctx)
    )


@main.command("get-hex")
@click.argument("string", type=str)
@click.pass_context
def local_hex(ctx: click.Context, string: str):
    """ Get all hexadecimal of the string """
    def hex_for_string(inp: str) -> List[str]:
        return list(map(lambda c: hex(ord(c)), inp))

    normalized = normalize(string, _get_unorm(ctx))
    normalized_list = [f" {char}" for char in normalized]
    print(tabulate.tabulate(
        list(
            zip(normalized_list, hex_for_string(string))
        ), headers=["Character", "Unicode Codepoint"], tablefmt="pipe", stralign="center"
    ))


def main_wrap():
    main(obj={})


if __name__ == "__main__":
    main_wrap()
