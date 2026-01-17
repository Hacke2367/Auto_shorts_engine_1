from manim import *
from src.config import *
from src.utils import *

# Directories check kar lo
setup_directories()


class TestBorder(Scene):
    def construct(self):
        # 1. Branding Border lao
        border = get_branding_border()

        # 2. Text check karo (Custom Font ke sath)
        welcome_text = Text("SYSTEM READY", font=get_font("Bold"), font_size=48)
        sub_text = Text("Gradient Border Test", font=get_font("Regular"), font_size=24, color=Theme.TEXT_SUB)

        # Positioning
        welcome_text.move_to(UP * 0.5)
        sub_text.next_to(welcome_text, DOWN)

        # 3. Screen pe dikhao (Animation ke sath)
        self.play(DrawBorderThenFill(border), run_time=1.5)
        self.play(Write(welcome_text), FadeIn(sub_text))

        # Thodi der ruko
        self.wait(2)