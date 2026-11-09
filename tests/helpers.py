"""Build rooms from short TOML snippets."""

from cutlist_optimiser.config import loads

SHEETS = """
[sheets]
size = [1200, 800]
thickness = 12
kerf = {kerf}
joint_gap = {joint_gap}
bottom_gap = {bottom_gap}
noggin_joints = "{noggin_joints}"
"""


def room(walls, height=2400, closed=False, kerf=3, joint_gap=3, bottom_gap=2, noggin_joints="prefer", extra=""):
    text = f"height = {height}\nclosed = {str(closed).lower()}\n"
    text += SHEETS.format(kerf=kerf, joint_gap=joint_gap, bottom_gap=bottom_gap, noggin_joints=noggin_joints)
    text += extra + "\n" + walls
    return loads(text)
