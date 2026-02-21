# Repository Guidelines

## Project Structure & Module Organization
- `src/templates/` contains Manim scene implementations (e.g., bar and butterfly charts).
- `src/utils.py` is the shared visual utility layer (`Brand`, safe-frame helpers, `IntroManager`, overlays/watermarks). Edit the active section below the second `utils.py` header; the top block is legacy commented code.
- `src/captions/` handles script loading, ASS rendering, and subtitle burn-in.
- `jobs/<job_id>/` is the unit of execution: `job.json`, `audio/`, `script/`, optional `data/`, plus generated `media/` and `output/`.
- `assets/` stores reusable fonts, images, and SFX; `data/` stores CSV inputs.

## Setup & Environment
- Use Python 3.11+ and create a virtual environment: `python -m venv .venv`.
- Install dependencies: `pip install -r requirements.txt`.
- Ensure FFmpeg is installed and discoverable: `ffmpeg -version`.

## Build, Test, and Development Commands
- `python main.py --job jobs/job_0001 --template bar_chart -q h` runs render + audio mix + optional captions.
- `python main.py --job jobs/butterfly_job --template butterfly_chart -q h --no_sfx` runs the butterfly job without SFX mixing.
- `python captions.py --job jobs/job_0001 --burn` regenerates ASS subtitles and burns them into video.
- `python -m manim -qh src/templates/Bar_chart/bar_chart.py BarChartTemplate --media_dir jobs/job_0001/media` renders one scene directly.

## Job Configuration Conventions
- Keep `audio.segments[].name` and `audio.order[]` consistent within each `job.json`.
- `timeline` must provide duration for every ordered segment used in mixing/captions.
- Store final outputs under `output/` (`final.mp4`, `subtitles.ass`, optional `final_captioned.mp4`).

## Coding Style & Naming Conventions
- Python style: 4-space indentation, snake_case for functions/variables, PascalCase for `Scene` classes.
- Use `pathlib.Path` for file paths and repo-relative resolution.
- No enforced formatter/linter yet; if adding automation, use `black`, `ruff`, and `pytest`.

## Commit & Pull Request Guidelines
- Follow existing concise commit style (short plain-language messages).
- PRs should include: what changed, which job/template was validated, and visual proof (screenshot or output clip path).

## Generated Artifacts
- `media/` and `jobs/*/output/` contain large generated files. Do not commit regenerated artifacts unless explicitly required for review.
