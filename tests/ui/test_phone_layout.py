"""Every page works on a phone: at 375 px wide, nothing pushes the page sideways.

Wide tables may scroll inside their own box; the page itself must not.
"""

from __future__ import annotations

import pytest

from tests.support import insert_claim
from tests.ui.pages import BasePage

PHONE = {"width": 375, "height": 740}
LONG_TITLE = "Return flight and two nights near the venue for the regional planning workshop"


@pytest.mark.parametrize(
    ("role", "path"),
    [
        pytest.param("employee", "/", id="dashboard"),
        pytest.param("employee", "/claims/new", id="new-claim"),
        pytest.param("manager", "/approvals", id="approvals"),
        pytest.param("finance", "/payments", id="payments"),
    ],
)
def test_the_page_fits_a_phone_screen_without_sideways_scrolling(
    role, path, db, sign_in, page, employee, manager, finance
):
    insert_claim(db, employee, "submitted", title=LONG_TITLE, category="travel", amount="1234.56")
    insert_claim(db, employee, "approved", title=LONG_TITLE, category="travel", amount="1234.56")
    sign_in({"employee": employee, "manager": manager, "finance": finance}[role])
    page.set_viewport_size(PHONE)

    page.goto(path)

    assert BasePage(page).scroll_width() <= PHONE["width"]
