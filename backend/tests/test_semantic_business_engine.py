from app.ai.catalog import catalog_for
from app.ai.compiler import deterministic_compile
from app.ai.contracts import ConversationState, QueryGoal


def compile_business(message):
    catalog = catalog_for("gym")
    query = deterministic_compile(
        message, catalog, context=None, state=ConversationState(),
    )
    if query:
        catalog.validate(query)
    return query


def test_named_client_compiles_to_a_profile_not_record_search():
    query = compile_business("Who is Priya Nair?")

    assert query.goal == QueryGoal.PROFILE
    assert query.entity == "client"
    assert query.entities[0].label == "Priya Nair"


def test_business_lists_and_revenue_use_the_same_semantic_contract():
    clients = compile_business("Show active clients")
    revenue = compile_business("Show revenue")

    assert clients.goal == QueryGoal.LIST
    assert clients.entity == "client"
    assert revenue.goal == QueryGoal.AGGREGATE
    assert revenue.entity == "sale"


def test_uncertain_general_question_is_not_converted_to_record_search():
    assert compile_business("Who is the best?") is None
