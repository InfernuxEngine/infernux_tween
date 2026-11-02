"""Native path preprocessing, immutable jobs and released-GIL buffer execution."""
from array import array
from concurrent.futures import ThreadPoolExecutor
import threading
import sys

import pytest

from infernux.lib import Vector3
from infernux_tween import Path, PathType
from infernux.lib._Infernux import _MotionPathSnapshot


def test_small_path_construction_keeps_gil_and_large_compile_releases_it():
    armed, observed = threading.Event(), threading.Event()
    def observe():
        armed.wait()
        observed.set()
    previous = sys.getswitchinterval()
    worker = threading.Thread(target=observe)
    try:
        sys.setswitchinterval(10)
        worker.start()
        armed.set()
        small = _MotionPathSnapshot([(0, 0, 0), (1, 2, 3)], 0, 10, False)
        assert small.length > 0 and not observed.is_set()
        large = _MotionPathSnapshot([(0, 0, 0), (1, 2, 3), (3, 1, 5)], 1, 200000, False)
        assert large.length > small.length and observed.is_set()
    finally:
        sys.setswitchinterval(previous)
        armed.set()
        worker.join(timeout=5)


@pytest.mark.parametrize("kind", list(PathType))
@pytest.mark.parametrize("closed", [False, True])
def test_precompiled_batch_matches_live_path_and_is_not_changed_by_author_edits(kind, closed):
    points = [(2, 3, 1), (0, 4, 2), (4, 1, 2)]
    path = Path((1, 2, 3), points, kind, 17, closed)
    snapshot = path.compile()
    progress = array("d", [-.2, 0, .125, .5, .99, 1, 1.2])
    output = array("f", [0]) * (3 * len(progress))
    snapshot.sample_into(progress, output)
    for index, expected in enumerate(path.point(time) for time in progress):
        assert list(output[3 * index:3 * index + 3]) == pytest.approx(tuple(expected), abs=3e-5)
        assert tuple(snapshot.sample(progress[index])) == tuple(output[3 * index:3 * index + 3])
        parameter = path.parameter_at(progress[index])
        assert tuple(snapshot.evaluate(parameter)) == tuple(path.evaluate(parameter))
    saved = list(output)
    path.points[1] = Vector3(30, 20, 10)
    snapshot.sample_into(progress, output)
    assert list(output) == saved
    assert tuple(path.evaluate(1)) != pytest.approx(tuple(snapshot.sample_many([1 / path.segments])[0]))


@pytest.mark.parametrize('kind',[PathType.CATMULL_ROM,PathType.CUBIC_BEZIER])
def test_raw_negative_curve_parameter_reports_an_index_error_while_progress_is_clamped(kind):
    path=Path((0,0,0),[(2,3,1),(0,4,2),(4,1,2)],kind,17)
    with pytest.raises(IndexError):
        path.evaluate(-.1)
    assert tuple(path.point(-.1)) == (0,0,0)


def test_numpy_matrix_and_standard_library_buffers_use_the_same_native_loop():
    import numpy as np
    path = Path((0, 0, 0), [(1, 2, 3), (3, 1, 5)], PathType.CATMULL_ROM)
    snapshot = path.compile()
    progress = np.linspace(0, 1, 257, dtype=np.float64)
    output = np.empty((257, 3), dtype=np.float32)
    snapshot.sample_into(progress, output)
    samples = snapshot.sample_many(progress)
    assert output == pytest.approx(np.array([tuple(value) for value in samples], dtype=np.float32), abs=3e-5)
    snapshot.sample_into(progress[:0], output[:0])
    with pytest.raises(ValueError, match="contiguous"):
        snapshot.sample_into(progress[::2], np.empty((129, 3), dtype=np.float32))
    with pytest.raises(ValueError, match="overlap"):
        storage = bytearray(48)
        snapshot.sample_into(memoryview(storage)[:16].cast("d"), memoryview(storage)[:24].cast("f"))


@pytest.mark.parametrize("kind", list(PathType))
def test_translated_finalized_path_keeps_tables_and_original_snapshot(kind):
    path = Path((1, 2, 3), [(2, 3, 1), (0, 4, 2), (4, 1, 2)], kind, 31)
    original = path._tables
    saved = [tuple(point) for point in original.sample_many([0, .25, .75, 1])]
    path._translate(Vector3(18, -2, 4))
    assert path._tables.length == original.length
    assert path._tables.parameters == original.parameters
    assert path._tables.distances == original.distances
    assert path._tables.waypoint_distances == original.waypoint_distances
    assert [tuple(point) for point in original.sample_many([0, .25, .75, 1])] == saved
    for time in [0, .25, .75, 1, 1.00001]:
        assert tuple(path._tables.sample(time)) == tuple(path.point(time))


def test_large_translation_releases_gil_and_captures_its_mutable_offset():
    original = _MotionPathSnapshot([(0, 0, 0)] * 100000, 0, 1, False)
    offset = Vector3(18, -2, 4)
    armed, observed = threading.Event(), threading.Event()
    def mutate():
        armed.wait()
        offset.x = 999
        observed.set()
    previous = sys.getswitchinterval()
    worker = threading.Thread(target=mutate)
    try:
        sys.setswitchinterval(10)
        worker.start()
        armed.set()
        translated = original.translated(offset)
        assert observed.is_set()
        assert tuple(translated.sample(0)) == (18, -2, 4)
        assert tuple(translated.sample(1)) == (18, -2, 4)
        assert tuple(original.sample(0)) == (0, 0, 0)
    finally:
        sys.setswitchinterval(previous)
        armed.set()
        worker.join(timeout=5)


def test_one_immutable_path_can_sample_separate_worker_owned_buffers():
    snapshot = Path((0, 0, 0), [(1, 2, 3), (3, 1, 5)], PathType.CATMULL_ROM).compile()
    def work(value):
        progress = array("d", [value]) * 10000
        output = array("f", [0]) * 30000
        snapshot.sample_into(progress, output)
        assert output[:3] == output[-3:]
        return tuple(output[:3])
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(work, [0, .25, .75, 1]))
    assert values[0] == (0, 0, 0) and values[-1] == (3, 1, 5)
    assert len(set(values)) == 4


def test_path_bulk_sampling_releases_gil_while_other_python_work_progresses():
    snapshot = Path((0, 0, 0), [(1, 2, 3), (3, 1, 5)], PathType.CATMULL_ROM).compile()
    progress, output = array("d", [.5]) * 250000, array("f", [0]) * 750000
    ready, stopped, counter = threading.Event(), threading.Event(), [0]
    def work():
        ready.set()
        while not stopped.is_set():
            counter[0] += 1
    thread = threading.Thread(target=work)
    thread.start()
    ready.wait()
    try:
        before = counter[0]
        snapshot.sample_into(progress, output)
        assert counter[0] > before + 100
    finally:
        stopped.set()
        thread.join(timeout=5)
