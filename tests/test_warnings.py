import warnings
from unittest.mock import MagicMock

import pytest

from fast_bitrix24.utils import get_warning_stack_level


async def empty_async(*args, **kwargs):
    pass


@pytest.mark.asyncio
async def test_warning_get_all(bx_dummy_async, monkeypatch):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        monkeypatch.setattr(
            "fast_bitrix24.user_request.GetAllUserRequest.run",
            lambda *args, **kwargs: empty_async(),
        )
        await bx_dummy_async.get_all("crm.deal.add")
    assert len(w) == 1
    print(w[0])
    assert w[0].filename == __file__  # Assuming the test is in the same file


@pytest.mark.asyncio
async def test_warning_get_all_params(bx_dummy_async, monkeypatch):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        monkeypatch.setattr(
            "fast_bitrix24.user_request.GetAllUserRequest.run",
            lambda *args, **kwargs: empty_async(),
        )
        await bx_dummy_async.get_all("crm.deal.list", params={"filter": {"ID": None}})
    assert len(w) == 1
    print(w[0])
    assert w[0].filename == __file__  # Assuming the test is in the same file



def mock_stack(filenames):
    frames = []
    for filename in filenames:
        frame = MagicMock()
        frame.f_back = frames[-1] if frames else None
        frame.f_code.co_filename = filename
        frames.append(frame)
    return frames


def mock_get_frame(stack, depth):
    return stack[-1 - depth]


# Test cases for happy path
@pytest.mark.parametrize(
    "module_filenames, module_sequence, expected_stack_level, test_id",
    [
        (["utils.py"], ["base.py", "utils.py", "caller.py"], 2, "single_module"),
        (
            ["module2.py", "module1.py"],
            ["base.py", "module1.py", "module2.py", "caller.py"],
            3,
            "multiple_modules",
        ),
        (
            ["module.py"],
            ["base.py", "module.py", "intermediate.py", "caller.py"],
            3,
            "intermediate_module",
        ),
        (
            "module.py",
            ["base.py", "module.py", "caller.py"],
            2,
            "single_module_str_input",
        ),
    ],
)
def test_get_warning_stack_level_happy_path(
    module_filenames, module_sequence, expected_stack_level, test_id, monkeypatch
):
    # Arrange
    monkeypatch.setattr(
        "fast_bitrix24.utils.sys._getframe",
        lambda depth=0: mock_get_frame(mock_stack(module_sequence), depth),
    )

    # Act
    stack_level = get_warning_stack_level(module_filenames)

    # Assert
    assert stack_level == expected_stack_level


# Test cases for error cases
@pytest.mark.parametrize(
    "module_filenames, module_sequence, expected_exception, test_id",
    [
        (["utils.py"], ["unrelated.py", "caller.py"], ValueError, "unrelated_module"),
    ],
)
def test_get_warning_stack_level_error_cases(
    module_filenames, module_sequence, expected_exception, test_id, monkeypatch
):
    # Arrange
    monkeypatch.setattr(
        "fast_bitrix24.utils.sys._getframe",
        lambda depth=0: mock_get_frame(mock_stack(module_sequence), depth),
    )

    # Act & Assert
    with pytest.raises(expected_exception):
        get_warning_stack_level(module_filenames)
