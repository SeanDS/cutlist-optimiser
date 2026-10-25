# Cutlist Optimiser

Works out the fewest fixed-size sheets (plasterboard, plywood, OSB, ...) needed to line stud walls, with regularly or irregularly spaced studs, and gives you a cut list.

## Install

Needs Python 3.11 or newer and has no dependencies. Install it with pip, ideally inside a virtual environment:

    pip install git+https://github.com/SeanDS/cutlist-optimiser

or from a local clone:

    pip install .

## Use

    cutlist-optimiser example.toml                 # print the wall layout and cut list
    cutlist-optimiser example.toml --svg plan.svg  # also draw walls and cutting diagrams
    cutlist-optimiser example.toml -n 20000        # search longer (default 3000 iterations)

While it searches, a progress bar showing the current best sheet count is printed to stderr (only in a terminal).

Copy `example.toml` and edit it. All sizes are in mm.

* `sheet` is the sheet size, e.g. `[2400, 1200]`. The default is `[1200, 800]`.
* `studs` lists the distances between consecutive stud centres, from one end of the wall to the other. Vertical sheet edges are only ever put on these lines.
* `noggins` is set per wall, with one list for each stud bay (the gap between neighbouring studs). Each list gives the noggin centre heights from the floor in that bay. Use `[]` for a bay with no noggins. For example, `noggins = [[1180], [1230], []]` covers a wall with three bays. Noggins are usually staggered from bay to bay, so a horizontal joint across a column that spans several bays is checked bay by bay. `noggin_tolerance` (default 10) is how far a joint may be from a noggin's centre and still count as fixed to it. `noggin_joints` controls how noggins are used:
  * `prefer` (the default) puts horizontal joints on noggins when doing so costs no extra sheets.
  * `require` only allows horizontal joints that are on a noggin in every bay they cross.
  * `ignore` doesn't consider noggins at all.
* `stay_out` lists areas on a wall that get no sheets, such as windows or doors. Each one is written as `{ x = [from, to], y = [from, to] }`, with `x` measured from the wall start and `y` from the floor. Both `x` edges must be on studs, which is where the framing around an opening sits. Those studs always carry a vertical joint, and the columns under an opening are filled separately below and above it. An opening that reaches the floor or ceiling is fine.
* `bottom_gap` and `top_gap` are the gaps left at the floor and ceiling.
* `joint_gap` is the gap between neighbouring sheets. Half of it comes off each edge that meets another sheet.
* `kerf` is the blade width allowed between pieces cut from the same sheet. Set it to 0 if you score and snap.
* `min_piece` stops it producing thin strips when it splits a column's height.

## How it works

1. Each wall is split into columns. Every column starts and ends on a stud and is no wider than a sheet.
2. Each column is filled from the floor gap to the ceiling with a stack of pieces as wide as the column. A piece can be up to 1200 tall if the column is at most 800 wide, otherwise up to 800 tall.
3. All the pieces are packed onto sheets with a guillotine packer. Offcuts are reused and pieces may be rotated.
4. A local search tries different column splits and stack heights. It ranks layouts by sheets first, then the number of bays where a joint has no noggin, then number of pieces.

The output compares the sheet count with the area lower bound. If they match, the result is optimal. The search is a heuristic, so a higher `-n` or another `--seed` can sometimes save a sheet.

The SVG shows every wall with its studs, noggins (thick lines), stay-out areas (crossed out) and pieces. Below that, each sheet is drawn whole with its pieces marked on it. Red dashed lines are the guillotine cuts, numbered in the order to make them, and hatched areas are offcuts.

Piece labels look like `2.3b`: wall 2, column 3, piece b (a is the bottom). Write them on the pieces as you cut.

Not handled: staggering horizontal joints between neighbouring columns, and corner overlaps.
