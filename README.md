# Cutlist Optimiser

Plans the lining and tiling of stud-framed walls, with regularly or irregularly spaced studs. It has two modes, which read the same room description:

* **`sheets`** works out the fewest fixed-size sheets (plasterboard, plywood, OSB, ...) needed to line the walls, with sheet edges on the studs, and gives you a cut list.
* **`tiles`** sets out tiles on the finished walls so they look neat: centred on the feature you choose, continuing round corners, lined up with window sills. It then counts the tiles and cuts and gives you a cut list.

## Install

Needs Python 3.11 or newer. Install it with pip, ideally inside a virtual environment:

    pip install git+https://github.com/SeanDS/cutlist-optimiser

or from a local clone:

    pip install .

## Use

    cutlist-optimiser sheets example.toml                 # sheet layout and cut list
    cutlist-optimiser sheets example.toml --svg plan.svg  # also draw walls and cutting diagrams
    cutlist-optimiser sheets example.toml -n 20000        # search longer (default 3000 iterations)
    cutlist-optimiser sheets example.toml --seed 7        # use a different random seed (default 0)
    cutlist-optimiser sheets example.toml --stagger       # stagger horizontal joints by at least 200 mm
    cutlist-optimiser sheets example.toml --stagger 300   # ... or by at least 300 mm

    cutlist-optimiser tiles example.toml                  # tile layout, counts and cut list
    cutlist-optimiser tiles example.toml --svg tiles.svg  # also draw the tiled walls

    cutlist-optimiser -v ...                              # more messages (-vv for debugging)
    cutlist-optimiser --debug ...                         # show full tracebacks on errors

`-v` and `--debug` work before or after the mode name. Messages are coloured by level when shown in a terminal. If the input file has a problem, it says where and what to change. Progress bars go to stderr, and only appear in a terminal.

## The room file

Copy `example.toml` and edit it. All sizes are in mm. Everything is measured from the **bare framing**: `x` from the corner at the start of each wall, `y` from the floor.

Top level:

* `height`: floor to ceiling.
* `closed`: `true` (the default) if the walls go all the way round, so the last wall meets the first.

### Walls

List the walls in order round the room, each as a `[[walls]]` entry:

* `name`
* `length`: the bare framing, corner to corner. Sheet mode needs it. Tile mode can work from `measured_length` instead.
* `measured_length` (optional): the **boarded face**, corner to corner, measured into the corners before tiling. Tile mode uses it instead of the calculated length, and warns if they differ by more than 10 mm.
* `measured_from`: `"framing"` (default) or `"boarded"`. Says where this wall's stay-out `x` positions are measured from. After boarding you can't see the framing corner, so measure from the boarded one and set `"boarded"`.
* `studs`: stud centre positions from the wall start. The corner studs are implied.
* `noggins`: one list per stud bay (the gap between neighbouring studs) of noggin centre heights from the floor. Use `[]` for a bay without noggins. A wall with studs at `[600, 1200]` has three bays.
* `corner`: the corner between this wall and the next:
  * `type`: `inside`, `outside` or `open` (a free end).
  * `through`: `this` or `next`, the wall whose sheets and tiles run to the corner line. The other wall butts against it.
  * `tiles`: `continue` (default) carries the tile pattern round the corner; `fresh` restarts it.
* `tiles = { priority = 1 }` (optional): how much you care that this wall's tiles are centred. 1 is the most important after the start feature. Add `centre_on = "window"` (a stay-out name) or `centre_on = 1450` (an x position) to centre on something other than the middle of the wall.
* `stay_out`: areas left bare, such as windows, doors or a bath, each `{ name = "...", x = [from, to], y = [from, to], reveal = ..., only = ... }`:
  * `reveal = { depth = 150 }`: the opening's reveals are boarded and tiled, with mitred corners. `depth` runs from the boarded face to the window frame. Use `reveal = "none"` for no tiled reveal, e.g. a door lining or a bath edge. Tile mode needs one or the other.
  * `only = "sheets"` or `"tiles"` applies the area to one mode only. A bath, for example, is boarded behind but not tiled.

At an inside corner, the wall that runs through takes its sheets to the corner line. The other wall's sheets stop short by the sheet thickness, and its tiles by the sheet and tile thickness together. At an outside corner, the wall that runs through covers the other's sheet edge. Tiles are mitred there by default, so both walls' tiles run to the arris.

### `[sheets]`

* `size`: sheet size, default `[1200, 800]`.
* `thickness`: tile mode needs it too, to work out the finished sizes.
* `kerf`: blade width between pieces cut from one sheet. Use 0 for score-and-snap.
* `joint_gap`: gap between neighbouring sheets. Half of it comes off each edge that meets another sheet.
* `bottom_gap`, `top_gap`: gaps at the floor and ceiling.
* `min_piece`: the shortest piece allowed when a column is split in height.
* `noggin_joints`: `prefer` (default) puts horizontal joints on noggins when that costs no extra sheets; `require` only allows joints on a noggin in every bay they cross; `ignore` doesn't consider noggins.
* `noggin_tolerance` (default 10): how far a joint may be from a noggin centre and still count as on it.

### `[tiles]`

* `size`: tile width x height as laid.
* `thickness`: tile plus adhesive bed.
* `grout`: the nominal joint width, the same in every joint.
* `grout_options`: other widths the tool may use instead, e.g. `[1.5, 2, 2.5, 3]` to match your spacers. One width is chosen for the whole room, and the output says which.
* `pattern`: `grid` or `brick`.
* `offset`: the brick offset as a fraction of the tile width. Use 0.5 for half bond; 0.333 is better for tiles over 600 mm long.
* `min_cut`: the smallest cut piece allowed anywhere.
* `min_mitre`: the smallest piece with a mitred edge.
* `kerf`: blade width.
* `rotate`: whether tiles may be turned when cutting pieces from them.
* `spare`: percent extra to order for breakage.
* `bottom_gap`, `top_gap`: gaps at the floor and ceiling.
* `outside_corners`: `mitre` (default), `overlap` or `trim`. Window reveals are always mitred.
* `start`: the feature everything is set out from, a wall (`"East"`) or an opening (`"South.window"`).
* `start_align`: `tile` (a tile centred on the start feature), `joint` (a joint centred on it) or `either` (default, whichever works out better).
* `rows`: row height goals, most important first:
  * `"WALL.OPENING.sill"` (or `.bottom`): a row ends exactly at the sill.
  * `"WALL.OPENING.head"` (or `.top`): a row starts exactly at the head.
  * `"floor"`: a whole tile at the bottom.
  * `"ceiling"`: a whole tile at the top.

## How sheet mode works

1. Each wall is split into columns. Every column starts and ends on a stud and is no wider than a sheet. Stay-out areas must have their sides on studs.
2. Each column is filled from the floor gap to the ceiling with a stack of pieces as wide as the column.
3. All the pieces are packed onto sheets with a guillotine packer. Offcuts are reused.
4. A local search tries different column splits and stack heights. It ranks layouts by sheets first, then the number of bays where a joint has no noggin, then the number of pieces.

The output gives the layout of each wall, the sheet utilisation, the cuts, and the pieces to cut from each sheet. The sheet count is compared with a lower bound from the area: if they match, the result is optimal. The search is random, so a higher `-n` or another `--seed` can sometimes save a sheet. The seed used is printed, and the same file, `-n` and seed always give the same result.

`--stagger` offsets the horizontal joints in neighbouring columns by at least the given distance, which makes the wall stronger. It is ranked above the sheet count. Run without it to see what staggering costs.

The SVG shows every wall with its studs, noggins (thick lines), stay-out areas (crossed out) and pieces, then each sheet with its pieces and numbered cuts.

## How tile mode works

1. **Finished sizes.** Each wall's tiled face is worked out from the framing, the corners and the sheet and tile thicknesses, or from your measured boarded length. A grout joint goes into every inside corner. Openings with tiled reveals shrink by the sheet and tile thickness on each side.
2. **Rows** run level all round the room. A single setting places them: the tool tries row heights that meet each row goal and ranks them in your order.
3. **Columns.** Walls joined by `continue` corners share one grid, unfolded round the corner, so a cut tile carries on onto the next wall. Each chain of such walls is set out from one wall: the start feature's wall, otherwise its highest-priority wall. Other walls in the chain follow from their corners. Only the grout width can still nudge them, so to centre one exactly, make one of its corners `fresh`.
4. **The seam.** If the pattern goes all the way round a closed room, it can't meet itself again, so one corner restarts it. The tool puts the seam between the two least important walls, and says so.
5. **Ranking.** Layouts are ranked by:
   1. fewest pieces below the minimum size;
   2. the start feature centred (always on a tile or a joint);
   3. the first row goal, then the walls in priority order, then the other row goals;
   4. grout closest to nominal;
   5. fewest tiles.

   Every grout width, row height and anchor position is tried.
6. **Packing.** Cut pieces, including the mitred reveal pieces, are packed onto tiles to reuse offcuts.

The output covers:

* **Priorities as understood:** how close each came, as millimetres off and as a percentage, where 0 mm off is 100% and the worst possible miss is 0%. For any goal not met exactly, it says why, e.g. "lining it up exactly would leave 25 more pieces below the minimum size, e.g. 18 mm tall at North row 1". It also lists what happens at each corner and where the seam is.
* **Finished sizes:** boarded and tiled lengths, marked measured or calculated, with what to measure to check them, and the finished size of each opening.
* **Setting out:** row heights, a level line, and for each wall the first and last piece in each row with where the first joint falls.
* **Tiles:** tiles needed and to order, efficiency (tile area on the walls ÷ area of tiles used), and cuts (straight cuts, notches at 2 cuts each, and mitred edges). It also lists any pieces below the minimum size.
* **Cut list:** grouped by how each tile is cut.

The SVG draws each wall's tiled face with whole tiles, cut pieces and their sizes. Pieces below the minimum are red, mitred edges are red lines, and the centre line is dashed blue.
