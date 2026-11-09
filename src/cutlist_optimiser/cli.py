"""Command line interface."""

import os
import sys
import traceback

import click

from . import console
from .config import ConfigError, load
from .console import em, info

console.setup()


def _state(ctx):
    return ctx.ensure_object(console.State)


def _verbosity(ctx, param, value):
    state = _state(ctx)
    state.verbosity += value
    state.apply()


def _debug(ctx, param, value):
    state = _state(ctx)
    state.debug = state.debug or value
    state.apply()


def common_options(f):
    """-v and --debug, accepted both before and after the subcommand name."""
    f = click.option("-v", "--verbose", count=True, expose_value=False, callback=_verbosity,
                     help="Show more messages: -v for progress details, -vv for debugging.")(f)
    f = click.option("--debug", is_flag=True, expose_value=False, callback=_debug,
                     help="Show full error tracebacks (and debugging messages).")(f)
    return f


class Cli(click.Group):
    """Turns errors into explanations; tracebacks only with --debug."""

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except (click.exceptions.Exit, click.exceptions.Abort, click.ClickException):
            raise
        except BrokenPipeError:  # output piped into e.g. head, which stopped reading
            sys.stdout = open(os.devnull, "w")
            ctx.exit(0)
        except ConfigError as e:
            self._fail(ctx, (f"{em(e.where)}: " if e.where else "") + e.problem,
                       e.fix or "check the input file")
        except Exception as e:  # noqa: BLE001 - anything else is a bug; explain and hide the traceback
            self._fail(ctx, f"unexpected problem: {e}",
                       "run again with --debug to see the details, and please report it")

    @staticmethod
    def _fail(ctx, message, fix):
        if _state(ctx).debug:
            traceback.print_exc(file=sys.stderr)
        console.error(message, fix)
        ctx.exit(1)


def progress_bar(done, total, best, width=30):
    """One line on stderr, redrawn about once per percent."""
    if done != total and done % max(1, total // 100):
        return
    filled = width * done // max(total, 1)
    end = "\n" if done == total else ""
    click.echo(f"\rSearching [{'#' * filled}{'.' * (width - filled)}] {done}/{total}  best: {best}",
               nl=False, err=True)
    if end:
        click.echo(err=True)


def _load(path, mode):
    room = load(path)
    (room.require_sheets if mode == "sheets" else room.require_tiles)()
    info(f"read {em(len(room.walls))} walls from {em(path)}")
    return room


@click.group(cls=Cli, context_settings={"help_option_names": ["-h", "--help"]})
@common_options
def main():
    """Cutlist Optimiser: plan sheet and tile layouts for stud-framed walls.

    Both modes read the same TOML room description; see example.toml.
    """


@main.command()
@click.argument("config", metavar="ROOM.toml")
@click.option("-n", "--iterations", type=click.IntRange(1), default=3000, show_default=True,
              help="Search iterations.")
@click.option("--seed", type=int, default=0, show_default=True, help="Random seed for the search.")
@click.option("--svg", metavar="FILE", help="Also write a drawing of the layout and sheets.")
@click.option("--stagger", type=float, is_flag=False, flag_value=200.0, default=0.0, metavar="[MM]",
              help="Stagger horizontal joints in neighbouring columns by at least MM (200 if no value).")
@common_options
def sheets(config, iterations, seed, svg, stagger):
    """Lay out sheets on the studs and make a cut list."""
    from .drawing import sheets_svg
    from .report import sheets_report
    from .sheets import Solver

    room = _load(config, "sheets")
    room.sheets.stagger = stagger
    solver = Solver(room, seed)
    show = progress_bar if console.is_terminal() else None
    res = solver.solve(iterations, (lambda d, t, b: show(d, t, f"{b} sheets")) if show else None)
    sheets_report(solver, res, seed)
    if svg:
        sheets_svg(solver, res, svg)
        click.echo(f"\nDrawing written to {em(svg)}")
