import csv
import io

from app.exporter import suite_to_csv
from app.models import (
    ExecutionMode,
)
from app.models import (
    TestCase as Case,
)
from app.models import (
    TestCategory as Category,
)
from app.models import (
    TestDatum as Datum,
)
from app.models import (
    TestStep as Step,
)
from app.models import (
    TestSuite as Suite,
)


def sample_suite() -> Suite:
    return Suite(
        feature_name="Login",
        test_cases=[
            Case(
                id="TC-001",
                title="Valid login",
                objective="Confirm access",
                category=Category.SMOKE,
                priority="P0",
                execution_mode=ExecutionMode.AUTOMATION,
                feasibility_reason="Stable sign-in flow with an observable dashboard result",
                steps=[Step(action="Sign in", expected_result="Dashboard appears")],
                test_data=[
                    Datum(name="email", value="qa.user@example.test", purpose="Valid account")
                ],
            )
        ],
    )


def test_suite_to_csv_exports_expected_columns() -> None:
    rows = list(csv.DictReader(io.StringIO(suite_to_csv(sample_suite()).decode("utf-8-sig"))))
    assert rows[0]["ID"] == "TC-001"
    assert rows[0]["Category"] == "smoke"
    assert "Dashboard appears" in rows[0]["Steps"]
    assert rows[0]["Format"] == "normal"
    assert rows[0]["Execution Mode"] == "automation"
    assert "Stable sign-in flow" in rows[0]["Feasibility Reason"]
