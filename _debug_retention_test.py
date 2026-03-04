from manim import *
from src.sync.retention import hold_breathing

class HUDTest(Scene):
    def construct(self):
        # Create a dummy object to focus on
        center_box = Rectangle(width=4, height=3).set_stroke(WHITE, 2)
        txt = Text("FOCUS ITEM", font_size=36).move_to(center_box)
        self.add(center_box, txt)

        # Trigger the retention HUD for 4 seconds
        # This should render the brackets, hex stream, and sine waves
        hold_breathing(self, 4.0, focus=center_box, text=None)
