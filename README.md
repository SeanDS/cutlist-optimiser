# Cutlist Optimiser

Works out the fewest fixed-size sheets (plasterboard, plywood, OSB, ...) needed to line stud walls, with regularly or irregularly spaced studs, and gives you a cut list.

## Install (Arch Linux)

Needs Python 3.11 or newer and has no dependencies.

    sudo pacman -S python-pipx
    pipx install /path/to/cutlist-optimiser

You can also use a venv: `python -m venv .venv && .venv/bin/pip install .`

## Use

    cutlist-optimiser example.toml                 # print the wall layout and cut list
    cutlist-optimiser example.toml --svg plan.svg  # also draw it
    cutlist-optimiser example.toml -n 20000        # search longer (default 3000 iterations)

Copy `example.toml` and edit it. All sizes are in mm.

* `sheet` is the sheet size, e.g. `[2400, 1200]`. The default is `[1200, 800]`.
* `studs` lists the distances between consecutive stud centres, from one end of the wall to the other. Vertical sheet edges are only ever put on these lines.
* `noggins` lists noggin centre heights from the floor. Set it once for every wall or per wall. `noggin_joints` controls how they are used:
  * `prefer` (the default) puts horizontal joints on noggins when doing so costs no extra sheets.
  * `require` only allows horizontal joints on noggins.
  * `ignore` doesn't consider noggins at all.
* `bottom_gap` and `top_gap` are the gaps left at the floor and ceiling.
* `joint_gap` is the gap between neighbouring sheets. Half of it comes off each edge that meets another sheet.
* `kerf` is the blade width allowed between pieces cut from the same sheet. Set it to 0 if you score and snap.
* `min_piece` stops it producing thin strips when it splits a column's height.

## How it works

1. Each wall is split into columns. Every column starts and ends on a stud and is no wider than a sheet.
2. Each column is filled from the floor gap to the ceiling with a stack of pieces as wide as the column. A piece can be up to 1200 tall if the column is at most 800 wide, otherwise up to 800 tall.
3. All the pieces are packed onto sheets with a guillotine packer. Offcuts are reused and pieces may be rotated.
4. A local search tries different column splits and stack heights. It ranks layouts by sheets first, then joints not on a noggin, then number of pieces.

The output compares the sheet count with the area lower bound. If they match, the result is optimal. The search is a heuristic, so a higher `-n` or another `--seed` can sometimes save a sheet.

Piece labels look like `2.3b`: wall 2, column 3, piece b (a is the bottom). Write them on the pieces as you cut.

Not handled: openings (doors, windows), staggering horizontal joints between neighbouring columns, and corner overlaps.
