from sqlalchemy import select

from app.ai.local_executor import execute_local_query, run_local_result_page
from app.ai.local_intent import interpret_business_query, normalize_language
from app.ai.tools import _normalize_record_spec, run_result_page, tool_business_summary
from app.core.database import SessionLocal
from app.models import Client, Organization, SaleInvoice, SaleLine, User


PARAPHRASES = [
    "show active clients", "list inactive clients", "how many clients",
    "new clients this month", "show employees", "list active staff",
    "show products", "list services", "show low stock",
    "show out of stock inventory", "show stock movements", "show appointments today",
    "list cancelled bookings", "how many appointments this week", "show unpaid invoices",
    "list paid invoices", "today collection", "payment history", "show overdue tasks",
    "list completed tasks", "memberships expiring this week", "show frozen memberships",
    "weekly check-ins", "show today attendance", "list gym classes", "show equipment",
    "overdue maintenance equipment", "show measurements", "show active goals",
    "show workouts", "show diet plans", "show coaching notes", "who needs attention",
    "show open commitments", "show salon preferences", "show patients", "show encounters",
    "show prescriptions", "show pending lab orders", "show failed messages",
    "show notifications", "show locations", "revenue by location", "appointments by branch",
    "compare this month revenue versus last month", "which products sold the most",
    "top clients", "show check-in trend", "how many memberships",
    "show invoices above INR 1000", "list products under rs 500", "show sales",
]


def _demo_user(db):
    organization = db.execute(select(Organization).where(
        Organization.slug == "pulse-fitness",
    )).scalar_one()
    return db.execute(select(User).where(
        User.organization_id == organization.id,
    ).order_by(User.created_at)).scalars().first()


def test_multilingual_normalization_and_precision_gate():
    assert normalize_language("Innaiku collection evlo?")[1] == "tanglish"
    assert normalize_language("இன்று வருகை எத்தனை?")[1] == "ta"

    with SessionLocal() as db:
        user = _demo_user(db)
        matches = [interpret_business_query(db, user, phrase, None, {}) for phrase in PARAPHRASES]

    precision = sum(match.outcome == "local" for match in matches) / len(matches)
    assert precision >= 0.98
    assert matches[10].query.intent == "stock_movements.find"
    assert matches[36].query.intent == "encounters.find"
    assert matches[47].query.intent == "checkins.trend"


def test_interpretation_is_conservative_for_reasoning_and_writes():
    with SessionLocal() as db:
        user = _demo_user(db)
        assert interpret_business_query(db, user, "Why did revenue drop?", None, {}).outcome == "fallback"
        assert interpret_business_query(db, user, "Create an appointment", None, {}).outcome == "fallback"
        assert interpret_business_query(db, user, "average client happiness", None, {}).outcome == "fallback"
        assert interpret_business_query(
            db, user, "list clients and sales in one combined report", None, {},
        ).outcome == "fallback"
        assert interpret_business_query(
            db, user,
            "show the item connected to every sale and customer in one combined report",
            None, {},
        ).outcome == "fallback"
        assert interpret_business_query(db, user, "show items", None, {}).outcome == "local"


def test_buyer_query_resolves_catalog_and_returns_only_matching_clients():
    with SessionLocal() as db:
        user = _demo_user(db)
        match = interpret_business_query(db, user, "clients who purchased resistance band", None, {})
        assert match.outcome == "local"
        assert match.query.intent == "purchases.buyers"
        assert match.query.entities[0].display_name == "Resistance Band"

        result = execute_local_query(db, user, match.query, "00000000-0000-0000-0000-000000000000")
        names = {item["display_name"] for item in result["tool_calls"][0]["result"]["items"]}
        assert names == {"Nila Suresh"}
        assert result["usage"]["provider_requests"] == 0
        assert result["usage"]["input_tokens"] == 0
        db.rollback()


def test_follow_up_reuses_validated_query_definition():
    with SessionLocal() as db:
        user = _demo_user(db)
        first = interpret_business_query(db, user, "show active clients", None, {})
        context = {"local_query": first.query.model_dump(mode="json")}
        follow_up = interpret_business_query(db, user, "what about last month", None, context)

    assert follow_up.outcome == "local"
    assert follow_up.query.subject == "clients"
    assert follow_up.query.status == "active"
    assert follow_up.query.date_range.label == "last month"


def test_explicit_new_subject_does_not_reuse_the_previous_scope():
    with SessionLocal() as db:
        user = _demo_user(db)
        first = interpret_business_query(db, user, "show active clients", None, {})
        context = {"local_query": first.query.model_dump(mode="json")}
        next_query = interpret_business_query(db, user, "show this month sales", None, context)

    assert next_query.outcome == "local"
    assert next_query.query.subject == "invoices"


def test_follow_up_can_select_an_ordinal_and_cross_to_invoices():
    with SessionLocal() as db:
        user = _demo_user(db)
        first = interpret_business_query(db, user, "show active clients", None, {})
        context = {
            "local_query": first.query.model_dump(mode="json"),
            "result_entities": [
                {"kind": "client", "id": "00000000-0000-0000-0000-000000000001", "display_name": "First"},
                {"kind": "client", "id": "00000000-0000-0000-0000-000000000002", "display_name": "Second"},
            ],
        }
        ordinal = interpret_business_query(db, user, "show the second one", None, context)
        unpaid = interpret_business_query(db, user, "which of them have unpaid invoices", None, context)

    assert ordinal.query.operation == "detail"
    assert ordinal.query.entities[0].display_name == "Second"
    assert unpaid.query.intent == "invoices.exceptions"
    assert unpaid.query.status == "overdue"
    assert len(unpaid.query.entities) == 2


def test_tanglish_latest_purchase_follow_up_returns_invoice_items_locally():
    with SessionLocal() as db:
        user = _demo_user(db)
        client = db.execute(select(Client).where(
            Client.organization_id == user.organization_id,
            Client.first_name == "Aarav",
        )).scalar_one()
        detail = interpret_business_query(db, user, "Tell me about Aarav Krishnan", None, {})
        context = {
            "local_query": detail.query.model_dump(mode="json"),
            "primary_entity": {
                "kind": "client", "id": client.id,
                "display_name": "Aarav Krishnan",
                "profile_ref": {"kind": "client", "id": client.id},
            },
        }

        match = interpret_business_query(
            db, user, "yes ivar kadisiya ena vaangirkaru", None, context,
        )
        result = execute_local_query(
            db, user, match.query, "00000000-0000-0000-0000-000000000000",
        )

        assert match.outcome == "local"
        assert match.query.intent == "purchases.history"
        assert result["usage"]["provider_requests"] == 0
        assert "Personal Training Session" in result["content"]
        item = result["tool_calls"][0]["result"]["items"][0]
        assert item["item"] == "Personal Training Session"
        assert item["invoice_number"] == "DEMO-GYM-0001"
        assert item["invoice_total_paise"] == 120000
        db.rollback()


def test_customer_count_and_follow_up_list_keep_the_same_active_scope():
    with SessionLocal() as db:
        user = _demo_user(db)
        count_match = interpret_business_query(
            db, user, "evlo customers irukaanga", None, {},
        )
        count_result = execute_local_query(
            db, user, count_match.query,
            "00000000-0000-0000-0000-000000000000",
        )
        context = {"local_query": count_match.query.model_dump(mode="json")}
        list_match = interpret_business_query(db, user, "who are they", None, context)
        tanglish_list = interpret_business_query(
            db, user, "antha count yaaru yaaru", None, context,
        )
        page = run_local_result_page(
            db, user, list_match.query.model_dump(mode="json"), 0, 100,
        )

        assert count_match.query.subject == "clients"
        assert count_match.query.status == "active"
        assert count_match.query.language == "tanglish"
        assert list_match.query.operation == "find"
        assert list_match.query.status == "active"
        assert tanglish_list.query.subject == "clients"
        assert count_result["tool_calls"][0]["result"]["value"] == page["count"]
        assert count_result["content"].startswith("Ippo ")
        db.rollback()


def test_follow_up_preserves_an_explicit_all_client_scope():
    with SessionLocal() as db:
        user = _demo_user(db)
        first = interpret_business_query(db, user, "all customers", None, {})
        context = {"local_query": first.query.model_dump(mode="json")}
        follow_up = interpret_business_query(db, user, "who are they", None, context)

    assert first.query.status is None
    assert follow_up.query.status is None


def test_client_summary_and_record_tool_use_the_same_scope():
    with SessionLocal() as db:
        user = _demo_user(db)
        summary = tool_business_summary(db, user)
        active = run_result_page(db, user, {
            "subject": "clients", "query": None, "location_id": None,
            "days": None, "status": "active", "created_within_days": None,
        }, 0, 100)

        assert summary["active_clients"] == active["count"]
        assert _normalize_record_spec("clients", query="customers") == (
            _normalize_record_spec("clients", query="clients")
        )
        assert _normalize_record_spec("clients", query="all customers")["status"] == "all"


def test_partial_sales_are_filtered_and_include_customer_and_items():
    with SessionLocal() as db:
        user = _demo_user(db)
        match = interpret_business_query(db, user, "partially paid sales", None, {})
        local_page = run_local_result_page(
            db, user, match.query.model_dump(mode="json"), 0, 100,
        )
        tool_page = run_result_page(db, user, {
            "subject": "sales", "query": None, "location_id": None,
            "days": None, "status": "partially_paid", "created_within_days": None,
        }, 0, 100)

        assert match.query.subject == "invoices"
        assert match.query.status == "partially_paid"
        assert local_page["count"] == tool_page["count"]
        assert local_page["items"]
        for item in local_page["items"] + tool_page["items"]:
            assert item["status"] == "partially_paid"
            assert item["customer_name"]
            assert item["item_names"]
            assert item["item_count"] >= len(item["item_names"])
            assert item["pending_paise"] == item["total_paise"] - item["paid_paise"]
            assert item["profile_ref"]["kind"] == "invoice"


def test_invoice_item_follow_up_uses_connected_sale_lines_not_catalog():
    with SessionLocal() as db:
        user = _demo_user(db)
        invoice = db.execute(select(SaleInvoice).where(
            SaleInvoice.organization_id == user.organization_id,
            SaleInvoice.status == "partially_paid",
        ).order_by(SaleInvoice.created_at.desc())).scalars().first()
        expected = set(db.execute(select(SaleLine.item_name).where(
            SaleLine.invoice_id == invoice.id,
        )).scalars())
        initial = interpret_business_query(db, user, "partially paid sales", None, {})
        context = {
            "local_query": initial.query.model_dump(mode="json"),
            "result_entities": [{
                "kind": "invoice", "id": invoice.id,
                "display_name": invoice.invoice_number,
                "profile_ref": {"kind": "invoice", "id": invoice.id},
            }],
        }

        follow_up = interpret_business_query(db, user, "ena item athuu", None, context)
        page = run_local_result_page(
            db, user, follow_up.query.model_dump(mode="json"), 0, 100,
        )

        assert follow_up.outcome == "local"
        assert follow_up.query.subject == "purchases"
        assert follow_up.query.language == "tanglish"
        assert follow_up.query.entities[0].kind == "invoice"
        assert {item["item"] for item in page["items"]} == expected
        assert {item["invoice_number"] for item in page["items"]} == {invoice.invoice_number}


def test_language_is_classified_from_each_current_turn():
    assert normalize_language("ena item athuu")[1] == "tanglish"
    assert normalize_language("What item was sold?")[1] == "en"
    assert normalize_language("வாடிக்கையாளர்கள் எத்தனை?")[1] == "ta"

    with SessionLocal() as db:
        user = _demo_user(db)
        english = interpret_business_query(db, user, "how many customers", None, {})
        tanglish = interpret_business_query(db, user, "customers evlo irukaanga", None, {})

        assert english.query.language == "en"
        assert tanglish.query.language == "tanglish"
