from manim import *

class QuickCacheTest(Scene):
    def construct(self):
        # A blisteringly fast 1-frame render that proves Manim doesn't crash on exit
        self.add(Text("CACHE TEST OK", font_size=24))
        self.wait(0.1)
