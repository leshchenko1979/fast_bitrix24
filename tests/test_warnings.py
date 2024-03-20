import warnings
import pytest

async def empty_async(*args, **kwargs):
    pass

@pytest.mark.asyncio
async def test_warning_get_all(bx_dummy_async, monkeypatch):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        monkeypatch.setattr("fast_bitrix24.user_request.GetAllUserRequest.run", lambda *args, **kwargs: empty_async())
        await bx_dummy_async.get_all("crm.deal.add")
    assert len(w) == 1
    print(w[0])
    assert w[0].filename == __file__  # Assuming the test is in the same file

@pytest.mark.asyncio
def test_warning_get_all_params(bx_dummy_async, monkeypatch):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        monkeypatch.setattr("fast_bitrix24.user_request.GetAllUserRequest.run", lambda *args, **kwargs: empty_async())
        await bx_dummy_async.get_all("crm.deal.list", params={"filter": {"ID": None}})
    assert len(w) == 1
    print(w[0])
    assert w[0].filename == __file__  # Assuming the test is in the same file

@pytest.mark.asyncio
async def test_warning_list_and_get(bx_dummy_async, monkeypatch):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        monkeypatch.setattr("fast_bitrix24.user_request.GetAllUserRequest.run", lambda *args, **kwargs: empty_async())
        await bx_dummy_async("crm.deal.list")
    assert len(w) == 1
    print(w[0])
    assert w[0].filename == __file__  # Assuming the test is in the same file
