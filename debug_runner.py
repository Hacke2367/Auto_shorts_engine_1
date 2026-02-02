
import sys
import traceback
from manim import *
import src.templates.Sort_card.sort_card as sc

try:
    config.media_dir = "./media"
    scene = sc.SortCardGodTierV4()
    scene.render()
except Exception:
    with open("traceback.txt", "w") as f:
        traceback.print_exc(file=f)
    print("CRASHED")
else:
    print("SUCCESS")
