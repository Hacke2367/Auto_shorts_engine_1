from manim import *
from src.sync.retention import hold_breathing

class RetentionTest(Scene):
    def construct(self):
        self.camera.background_color = "#050505"

        box = RoundedRectangle(width=5, height=2, corner_radius=0.2)
        box.set_fill(BLACK, opacity=0.6).set_stroke(WHITE, width=2)
        txt = Text("RETENTION TEST", font_size=36).move_to(box)

        self.play(FadeIn(box), Write(txt), run_time=0.8)

        # This MUST extend the video by ~6 seconds total
        hold_breathing(self, 6.0, focus=box)

        self.play(FadeOut(txt), FadeOut(box), run_time=0.6)
