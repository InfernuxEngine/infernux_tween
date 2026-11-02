"""The acceptance camera may have a different aspect ratio than its UI reference."""
import importlib.util
from pathlib import Path

import pytest

source=Path(__file__).parent/'acceptance/build_player_probe.py'
spec=importlib.util.spec_from_file_location('_player_image_geometry',source)
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize('width,height,bounds,center,static', [
    (640,360,(340,140,420,180),(380,160),(32,32)),
    (1280,720,(680,280,840,360),(760,320),(64,64)),
    (1706,767,(901,288,1091,383),(996,336),(76,76)),
    (1000,1000,(542,417,708,500),(625,458),(67,67)),
    (360,640,(200,280,280,320),(240,300),(32,32)),
])
def test_expected_ui_geometry_uses_uniform_canvas_scaling_and_pixel_centers(width,height,bounds,center,static):
    _,actual_bounds,actual_center,actual_static=probe.player_ui_geometry(width,height)
    assert (actual_bounds,actual_center,actual_static)==(bounds,center,static)
