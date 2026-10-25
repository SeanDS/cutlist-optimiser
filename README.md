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
    cutlist-optimiser example.toml --seed 7        # use a different random seed (default 0)
    cutlist-optimiser example.toml --stagger       # stagger horizontal joints by at least 200 mm
    cutlist-optimiser example.toml --stagger 300   # ... or by at least 300 mm

While it searches, a progress bar showing the current best sheet count is printed to stderr (only in a terminal).

Copy `example.toml` and edit it. All sizes are in mm.

* `sheet` is the sheet size, e.g. `[2400, 1200]`. The default is `[1200, 800]`.
* `studs` lists the distances between consecutive stud centres, from one end of the wall to the other. Vertical sheet edges are only ever put on these lines.
* `noggins` is set per wall, with one list for each stud bay (the gap between neighbouring studs). Each list gives the noggin centre heights from the floor in that bay. Use `[]` for a bay with no noggins. For example, `noggins = [[1180], [1230], []]` covers a wall with three bays. Noggins are usually staggered from bay to bay, so a horizontal joint across a column that spans several bays is checked bay by bay. `noggin_tolerance` (default 10) is how far a joint may be from a noggin's centre and still count as fixed to it. `noggin_joints` controls how noggins are used:
  * `prefer` (the default) puts horizontal joints on noggins when doing so costs no extra sheets.
  * `require` only allows horizontal joints that are on a noggin in every bay they cross.
  * `ignore` doesn't consider noggins at all.
* `stay_out` lists areas on a wall that get no sheets, such as windows or doors. Each one is written as `{ x = [from, to], y = [from, to] }`, with `x` measured from the wall start and `y` from the floor. Both `x` edges must be on studs, which is where the framing around an opening sits. Those studs always carry a vertical joint, and the columns under an opening are filled separately below and above it. An opening that reaches the floor or ceiling is fine.
* `start` and `end` set what happens at each end of a wall:
  * `full` (the default) runs the sheets to the end of the wall.
  * `inside` is an inside corner where this wall's sheets butt against the other wall's sheets. They stop short by `thickness`.
  * `outside` is an outside corner where this wall's sheets cover the other wall's sheet edge. They run past by `thickness`.

  At each corner, set one wall to `full` and the other to `inside` or `outside`. `example.toml` runs the North and South walls full length, and the East and West walls butt into them.
* `thickness` is the sheet thickness. You must set it to use `inside` or `outside` corners.
* `bottom_gap` and `top_gap` are the gaps left at the floor and ceiling.
* `joint_gap` is the gap between neighbouring sheets. Half of it comes off each edge that meets another sheet.
* `kerf` is the blade width allowed between pieces cut from the same sheet. Set it to 0 if you score and snap.
* `min_piece` stops it producing thin strips when it splits a column's height.

## How it works

1. Each wall is split into columns. Every column starts and ends on a stud and is no wider than a sheet.
2. Each column is filled from the floor gap to the ceiling with a stack of pieces as wide as the column. A piece can be up to 1200 tall if the column is at most 800 wide, otherwise up to 800 tall.
3. All the pieces are packed onto sheets with a guillotine packer. Offcuts are reused and pieces may be rotated.
4. A local search tries different column splits and stack heights. It ranks layouts by sheets first, then the number of bays where a joint has no noggin, then number of pieces.

The cut list starts with the sheet utilisation: how much of the bought sheet area ends up in pieces, and how much is wasted as offcuts and saw kerf. Each sheet also shows how much of it is used and how many cuts it needs, and the total number of cuts is given. Every straight cut is counted, including thin trims to size.

The output compares the sheet count with the area lower bound. If they match, the result is optimal. The search is a heuristic, so a higher `-n` or another `--seed` can sometimes save a sheet. The seed used is printed at the top of the output. The same file, `-n` and seed always give the same result.

The SVG shows every wall with its studs, noggins (thick lines), stay-out areas (crossed out) and pieces. Below that, each sheet is drawn whole with its pieces marked on it. Red dashed lines are the guillotine cuts, numbered in the order to make them, and hatched areas are offcuts.

`--stagger` offsets the horizontal joints in neighbouring columns of a wall by at least the given distance (200 mm if no value is given), which makes the wall stronger. It is ranked above the sheet count, so the search avoids lined-up joints even when that costs a sheet. Within that, it still uses the fewest sheets and puts joints on noggins where it can. Run without `--stagger` to see what staggering costs. Any joints it couldn't stagger are listed in the notes under the cut list.

Piece labels look like `2.3b`: wall 2, column 3, piece b (a is the bottom). Write them on the pieces as you cut.


