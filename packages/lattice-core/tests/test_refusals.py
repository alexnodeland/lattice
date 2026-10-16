"""The refusals a router documents."""

import pytest
from fastapi import APIRouter, FastAPI, HTTPException

from lattice_core.refusals import FieldError, Refused, RejectionDetail, refusals


def test_refusals_describe_each_status_with_the_refused_body() -> None:
    assert refusals(403, 422) == {
        403: {"model": Refused, "description": "Refused"},
        422: {"model": Refused, "description": "Refused"},
    }


@pytest.mark.parametrize(
    "body",
    [
        {"detail": {"type": "not_found", "message": "no such artifact", "id": "nope"}},
        {"detail": "unauthorized"},
        {"detail": [{"loc": ["query", "limit"], "msg": "too small", "type": "greater_than_equal"}]},
    ],
)
def test_refused_reads_each_shape_of_detail(body: dict[str, object]) -> None:
    detail = Refused.model_validate(body).detail
    assert isinstance(detail, RejectionDetail | str | list)
    if isinstance(detail, RejectionDetail):
        assert detail.model_dump()["id"] == "nope", "typed details are kept"
    elif isinstance(detail, list):
        assert isinstance(detail[0], FieldError)


def test_a_router_documents_the_refused_body() -> None:
    router = APIRouter(responses=refusals(400, 401, 403, 404, 409, 422))

    @router.get("/items")
    async def items() -> list[str]:
        raise HTTPException(404)

    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()
    responses = schema["paths"]["/items"]["get"]["responses"]
    assert {"400", "401", "403", "404", "409", "422"} <= set(responses)
    assert responses["404"]["description"] == "Refused"
    assert set(schema["components"]["schemas"]) >= {"Refused", "RejectionDetail", "FieldError"}
