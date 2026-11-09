"""Terminal output: verbosity, coloured log messages and emphasis.

Messages go through the standard logging module so the verbosity level decides
what is shown: warnings and errors always, info with -v, debug with -vv.
click strips the colours automatically when output is not a terminal.
"""

import logging
import sys
from dataclasses import dataclass

import click

log = logging.getLogger("cutlist_optimiser")

STYLES = {
    logging.DEBUG: ("debug", {"dim": True}),
    logging.INFO: ("info", {"fg": "blue"}),
    logging.WARNING: ("warning", {"fg": "yellow", "bold": True}),
    logging.ERROR: ("error", {"fg": "red", "bold": True}),
}


@dataclass
class State:
    """Shared by the top-level command and its subcommands through click's context object."""
    verbosity: int = 0
    debug: bool = False

    def apply(self):
        level = logging.DEBUG if self.debug or self.verbosity >= 2 else (
            logging.INFO if self.verbosity == 1 else logging.WARNING)
        log.setLevel(level)


class _Handler(logging.Handler):
    def emit(self, record):
        name, style = STYLES.get(record.levelno, ("", {}))
        click.echo(f"{click.style(name + ':', **style)} {record.getMessage()}", err=True)


def setup():
    if not any(isinstance(h, _Handler) for h in log.handlers):
        log.addHandler(_Handler())
        log.propagate = False
    if log.level == logging.NOTSET:
        log.setLevel(logging.WARNING)


def em(value):
    """Emphasise a value inside a message."""
    return click.style(str(value), bold=True)


def heading(text):
    return click.style(text, bold=True, underline=True)


def debug(msg):
    log.debug(msg)


def info(msg):
    log.info(msg)


def warning(msg):
    log.warning(msg)


def error(msg, fix=None):
    log.error(msg)
    if fix:
        click.echo(f"  {click.style('fix:', fg='green', bold=True)} {fix}", err=True)


def is_terminal(stream=None):
    return (stream or sys.stderr).isatty()
