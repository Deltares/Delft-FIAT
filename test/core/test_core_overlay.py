import numpy as np

from fiat._core import cell_mask, clip_masked


def test_clip_masked():
    # Set a small window and a selection mask
    arr = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float64)
    mask = np.array([[0.0, 1.0, 1.0], [1.0, 0.0, 1.0]], dtype=np.float64)

    # Call the function
    out = clip_masked(arr, mask, 0.0, 0)

    # Assert the selected cells are gathered in row-major order
    assert out.dtype == np.float64
    np.testing.assert_array_equal(out, [2.0, 3.0, 4.0, 6.0])


def test_clip_masked_nodata():
    # A window holding a nodata value
    arr = np.array([[1.0, -9999.0], [3.0, 4.0]], dtype=np.float64)
    mask = np.ones(arr.shape, dtype=np.float64)

    # Call the function with the nodata flag on
    out = clip_masked(arr, mask, -9999.0, 1)

    # Assert nodata was mapped to nan
    assert np.isnan(out[1])
    np.testing.assert_array_almost_equal(out[[0, 2, 3]], [1.0, 3.0, 4.0])


def test_clip_masked_no_nodata():
    arr = np.array([[1.0, -9999.0], [3.0, 4.0]], dtype=np.float64)
    mask = np.ones(arr.shape, dtype=np.float64)

    # Call the function with the nodata flag off
    out = clip_masked(arr, mask, -9999.0, 0)

    # Assert the raw values are kept
    np.testing.assert_array_equal(out, [1.0, -9999.0, 3.0, 4.0])


def test_clip_masked_float32():
    # A float32 window should still yield a float64 result
    arr = np.array([[1.5, 2.5], [3.5, 4.5]], dtype=np.float32)
    mask = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float64)

    # Call the function
    out = clip_masked(arr, mask, 0.0, 0)

    # Assert the output
    assert out.dtype == np.float64
    np.testing.assert_array_almost_equal(out, [1.5, 4.5])


def test_clip_masked_empty():
    # An empty selection yields an empty array
    arr = np.array([[1.0, 2.0]], dtype=np.float64)
    mask = np.zeros(arr.shape, dtype=np.float64)

    # Call the function
    out = clip_masked(arr, mask, 0.0, 0)

    # Assert the output
    assert out.dtype == np.float64
    assert out.shape == (0,)


def test_cell_mask_line(
    footprint_xy: np.ndarray,
    footprint_ends: np.ndarray,
):
    # Call the function for a non-areal geometry, only segments hit
    mask = cell_mask(footprint_xy, footprint_ends, 0, 0.0, 0.0, 1.0, -1.0, 3, 3)

    # Assert the interior cell is not covered
    np.testing.assert_array_equal(
        mask,
        [[1.0, 1.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 1.0]],
    )


def test_cell_mask_areal(
    footprint_xy: np.ndarray,
    footprint_ends: np.ndarray,
):
    # Call the function for an areal geometry, interior counts as covered
    mask = cell_mask(footprint_xy, footprint_ends, 1, 0.0, 0.0, 1.0, -1.0, 3, 3)

    # Assert every cell is covered
    np.testing.assert_array_equal(mask, np.ones((3, 3), dtype=np.float64))
