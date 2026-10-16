"""The FastAPI app: JSON API routes, server-rendered pages and error handlers.

Run it with ``python -m uvicorn expenses.main:app --port 8000``. Sign-in is an
``X-User`` header or a ``user`` cookie naming a user; there are no passwords.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote, unquote

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from starlette.exceptions import HTTPException as StarletteHTTPException

from expenses import bugs, db, rules, service

HERE = Path(__file__).parent
USER_COOKIE = "user"
FLASH_COOKIE = "flash"

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Refuse to start on an unknown SEEDED_BUG, then make sure the schema and demo users exist."""
    seeded = bugs.current()
    if seeded:
        log.warning("SEEDED_BUG=%s is active: %s", seeded, bugs.CATALOG[seeded])
    db.init_db()
    yield


app = FastAPI(title="Expenses", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def _money(cents: int) -> str:
    return f"${Decimal(cents) / 100:,.2f}"


def _label(value: str) -> str:
    return value.capitalize()


_env = Environment(
    loader=FileSystemLoader(HERE / "templates"),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["money"] = _money
_env.filters["label"] = _label
_env.globals["bug_active"] = bugs.active
_env.globals["categories"] = rules.CATEGORIES
_env.globals["category_limits"] = rules.CATEGORY_LIMITS
_env.globals["mileage_rate"] = rules.MILEAGE_RATE
templates = Jinja2Templates(env=_env)


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "invalid_transition",
    422: "validation",
}


def _error(
    status: int, code: str, detail: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse({"error": code, "detail": detail}, status_code=status, headers=headers)


@app.exception_handler(rules.ClaimError)
async def _claim_error(_: Request, exc: rules.ClaimError) -> JSONResponse:
    return _error(exc.status, exc.code, exc.detail)


@app.exception_handler(RequestValidationError)
async def _request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    parts = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        parts.append(f"{where}: {err.get('msg')}" if where else str(err.get("msg")))
    return _error(422, "validation", "; ".join(parts) or "The request is not valid.")


def _http_code(status: int) -> str:
    """The error code for a framework HTTP error, always one that error.schema.json lists."""
    return _HTTP_CODES.get(status, "internal" if status >= 500 else "bad_request")


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _http_code(exc.status_code)
    return _error(exc.status_code, code, str(exc.detail), headers=exc.headers)


@app.exception_handler(Exception)
async def _unexpected_error(_: Request, _exc: Exception) -> JSONResponse:
    return _error(500, "internal", "The server hit an unexpected error.")


def api_user(request: Request) -> service.User:
    """The caller, from the X-User header or else the user cookie. 401 when missing or unknown."""
    username = request.headers.get("x-user") or request.cookies.get(USER_COOKIE)
    user = service.get_user(username)
    if user is None:
        raise rules.Unauthenticated("Sign in first: send an X-User header or the user cookie.")
    return user


async def json_body(request: Request) -> object:
    """The parsed JSON body, or None when the body is empty. 422 when it is not JSON."""
    raw = await request.body()
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise rules.ValidationError("The request body is not valid JSON.") from exc


async def form_fields(request: Request) -> dict[str, str]:
    """The posted HTML form as a plain dict of strings."""
    form = await request.form()
    return {key: value for key, value in form.items() if isinstance(value, str)}


ApiUser = Annotated[service.User, Depends(api_user)]
JsonBody = Annotated[object, Depends(json_body)]
FormFields = Annotated[dict[str, str], Depends(form_fields)]


def _claim_response(row: service.Claim, status: int = 200) -> JSONResponse:
    headers = {"Location": f"/api/claims/{row['id']}"} if status == 201 else None
    return JSONResponse(service.claim_json(row), status_code=status, headers=headers)


@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness, plus which seeded bug (if any) this process runs."""
    return {"status": "ok", "seededBug": bugs.current()}


@app.get("/api/me")
def me(user: ApiUser) -> dict[str, str]:
    return {"username": user.username, "displayName": user.display_name, "role": user.role}


@app.post("/api/claims")
def create_claim(user: ApiUser, body: JsonBody) -> JSONResponse:
    """Submit a claim. 201 with the claim."""
    if not isinstance(body, dict):
        raise rules.ValidationError("The request body must be a JSON object.")
    return _claim_response(service.create_claim(user, body), status=201)


@app.get("/api/claims")
def list_claims(user: ApiUser, status: str | None = None) -> dict[str, Any]:
    """The claims the caller may see, ordered by id, optionally filtered by status."""
    rows = service.list_claims(user, rules.parse_status_filter(status))
    return {"claims": [service.claim_json(row) for row in rows]}


@app.get("/api/claims/{claim_id}")
def get_claim(user: ApiUser, claim_id: int) -> JSONResponse:
    return _claim_response(service.get_claim(user, claim_id))


@app.post("/api/claims/{claim_id}/approve")
def approve_claim(user: ApiUser, claim_id: int) -> JSONResponse:
    """Approve a submitted claim (managers, not their own)."""
    return _claim_response(service.approve(user, claim_id))


@app.post("/api/claims/{claim_id}/reject")
def reject_claim(user: ApiUser, claim_id: int, body: JsonBody) -> JSONResponse:
    """Reject a submitted claim with ``{"note": "..."}`` (managers, not their own)."""
    if body is not None and not isinstance(body, dict):
        raise rules.ValidationError("The request body must be a JSON object.")
    note = body.get("note") if isinstance(body, dict) else None
    return _claim_response(service.reject(user, claim_id, note))


@app.post("/api/claims/{claim_id}/pay")
def pay_claim(user: ApiUser, claim_id: int) -> JSONResponse:
    """Pay an approved claim (finance)."""
    return _claim_response(service.pay(user, claim_id))


@app.get("/api/summary")
def summary(user: ApiUser) -> dict[str, str]:
    """Totals of the caller's own claims as two-decimal strings."""
    return {key: rules.format_cents(cents) for key, cents in service.summary_cents(user).items()}


@app.get("/api/export.csv")
def export_csv(user: ApiUser) -> Response:
    """Approved and paid claims as CSV (finance)."""
    return Response(
        content=service.export_csv(user),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="claims.csv"'},
    )


def _page_user(request: Request) -> service.User | None:
    return service.get_user(request.cookies.get(USER_COOKIE))


def _to_login() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(USER_COOKIE)
    return response


def _redirect(url: str, message: str, kind: str = "ok") -> RedirectResponse:
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(FLASH_COOKIE, quote(f"{kind}:{message}"), httponly=True, samesite="lax")
    return response


def _render(request: Request, name: str, status: int = 200, **context: Any) -> HTMLResponse:
    flash = None
    raw = request.cookies.get(FLASH_COOKIE)
    if raw:
        kind, _, message = unquote(raw).partition(":")
        flash = {"kind": "error" if kind == "error" else "ok", "message": message}
    response = templates.TemplateResponse(
        request, name, {"flash": flash, **context}, status_code=status
    )
    if raw:
        response.delete_cookie(FLASH_COOKIE)
    return response


def _form_claim(fields: dict[str, str]) -> dict[str, str | None]:
    """Map the HTML form onto the API's field names. Empty inputs count as absent."""
    return {
        "title": fields.get("title", ""),
        "category": fields.get("category", ""),
        "amount": fields.get("amount") or None,
        "miles": fields.get("miles") or None,
        "expenseDate": fields.get("expense_date", ""),
    }


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    """The sign-in form: pick any user, no password."""
    return _render(request, "login.html", users=service.list_users(), active="login")


@app.post("/login", response_model=None)
def login(request: Request, fields: FormFields) -> Response:
    """Set the user cookie and go to the dashboard."""
    posted = fields.get("user", "")
    user = service.get_user(posted)
    username = user.username if user else None
    if bugs.active("login-trusts-the-form"):
        # SEEDED BUG login-trusts-the-form: the posted name goes into the cookie without the lookup.
        username = posted
    if username is None:
        return _render(
            request,
            "login.html",
            status=400,
            users=service.list_users(),
            error="Pick a user from the list.",
            active="login",
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(USER_COOKIE, username, httponly=True, samesite="lax")
    return response


@app.api_route("/logout", methods=["GET", "POST"])
def logout() -> RedirectResponse:
    """Clear the user cookie."""
    return _to_login()


@app.get("/", response_model=None)
def dashboard(request: Request) -> Response:
    """My claims, with totals."""
    user = _page_user(request)
    if user is None:
        return _to_login()
    return _render(
        request,
        "dashboard.html",
        user=user,
        claims=service.own_claims(user),
        totals=service.summary_cents(user),
        active="dashboard",
    )


def _new_claim_form(
    request: Request,
    user: service.User,
    values: dict[str, str],
    error: str | None = None,
    status: int = 200,
) -> HTMLResponse:
    return _render(
        request,
        "claim_form.html",
        status=status,
        user=user,
        values=values,
        error=error,
        today=rules.today_utc().isoformat(),
        active="dashboard",
    )


@app.get("/claims/new", response_model=None)
def new_claim_page(request: Request) -> Response:
    user = _page_user(request)
    if user is None:
        return _to_login()
    values = {"category": "meals", "expense_date": rules.today_utc().isoformat()}
    return _new_claim_form(request, user, values)


@app.post("/claims/new", response_model=None)
def new_claim(request: Request, fields: FormFields) -> Response:
    """Submit the form through the same service call as the API."""
    user = _page_user(request)
    if user is None:
        return _to_login()
    try:
        row = service.create_claim(user, _form_claim(fields))
    except rules.ClaimError as exc:
        return _new_claim_form(request, user, fields, error=exc.detail, status=exc.status)
    return _redirect("/", f"Claim #{row['id']} submitted.")


def _role_page(request: Request, role: str, template: str, active: str) -> Response:
    user = _page_user(request)
    if user is None:
        return _to_login()
    if user.role != role:
        return _render(
            request,
            "error.html",
            status=403,
            user=user,
            heading="Not allowed",
            message=f"This page is for the {role} role.",
        )
    claims = (
        service.awaiting_approval(user) if role == "manager" else service.awaiting_payment(user)
    )
    return _render(request, template, user=user, claims=claims, active=active)


@app.get("/approvals", response_model=None)
def approvals_page(request: Request) -> Response:
    """Submitted claims from other people, for managers."""
    return _role_page(request, "manager", "approvals.html", "approvals")


@app.get("/payments", response_model=None)
def payments_page(request: Request) -> Response:
    """Approved claims waiting for payment, for finance."""
    return _role_page(request, "finance", "payments.html", "payments")


def _page_action(
    request: Request, page: str, act: Callable[[service.User], object], done: str
) -> Response:
    """Run a button press (Approve, Reject, Pay) and go back to ``page`` with the outcome."""
    user = _page_user(request)
    if user is None:
        return _to_login()
    try:
        act(user)
    except rules.ClaimError as exc:
        message, kind = exc.detail, "error"
    else:
        message, kind = done, "ok"
    if bugs.active("page-ignores-refusal"):
        # SEEDED BUG page-ignores-refusal: the page reports success whatever the service said.
        message, kind = done, "ok"
    return _redirect(page, message, kind)


@app.post("/claims/{claim_id}/approve", response_model=None)
def approve_form(request: Request, claim_id: int) -> Response:
    return _page_action(
        request,
        "/approvals",
        lambda user: service.approve(user, claim_id),
        f"Claim #{claim_id} approved.",
    )


@app.post("/claims/{claim_id}/reject", response_model=None)
def reject_form(request: Request, claim_id: int, fields: FormFields) -> Response:
    return _page_action(
        request,
        "/approvals",
        lambda user: service.reject(user, claim_id, fields.get("note")),
        f"Claim #{claim_id} rejected.",
    )


@app.post("/claims/{claim_id}/pay", response_model=None)
def pay_form(request: Request, claim_id: int) -> Response:
    return _page_action(
        request,
        "/payments",
        lambda user: service.pay(user, claim_id),
        f"Claim #{claim_id} paid.",
    )
