import os

# Structural fallback for the incident agent (final-review C1, 2026-08-09): what
# sampler.spawn_agent() spins up is a real, paid opus subprocess, and no test file is allowed to
# trigger it by accident. Mocking out spawn_agent in each test file is the first line of
# defense; this environment variable is the second -- `tests` is a package, and
# `python3 -m unittest tests.test_x` always executes this __init__.py first, so setting it once
# here covers every test file in the whole package, and no individual file needs to remember to
# set it. When sampler.spawn_agent() sees this variable non-empty, it only writes a placeholder
# line and does not spawn a subprocess.
os.environ.setdefault("NEW1_NO_SPAWN", "1")
