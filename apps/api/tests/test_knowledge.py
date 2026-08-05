from sqlalchemy.orm import Session
from uuid import uuid4

from app.db.seed import seed_development_data
from app.db.session import engine
from app.models import KnowledgeDocument, KnowledgeFact, Product
from app.product_intelligence.contracts import ProductCandidate
from app.services.knowledge import product_knowledge, record_candidate_knowledge


def test_confirmed_candidate_preserves_document_and_facts() -> None:
    with engine.connect() as connection, connection.begin():
        session = Session(bind=connection)
        seed = seed_development_data(session)
        unique_name = f"ja steinofen pizza margherita {uuid4().hex}"
        product = Product(
            household_id=seed.household_id,
            canonical_name=unique_name,
            normalized_name=unique_name,
            product_type="food",
        )
        session.add(product)
        session.flush()
        candidate = ProductCandidate(
            canonical_name="ja! Steinofen Pizza Margherita 3x300g",
            provider="tavily_web",
            confidence=0.82,
            brand="ja!",
            product_type="food",
            source_url="https://www.rewe.de/shop/p/ja-pizza/123",
            nutrition={"energy_kcal": 220.0, "protein_g": 9.1},
            evidence={"source_content": "# ja! Pizza\n| Eiweiß | 9,1 g |"},
        )

        first = record_candidate_knowledge(
            session,
            household_id=seed.household_id,
            product=product,
            candidate=candidate,
            user_id=seed.user_id,
        )
        second = record_candidate_knowledge(
            session,
            household_id=seed.household_id,
            product=product,
            candidate=candidate,
            user_id=seed.user_id,
        )
        loaded, documents = product_knowledge(
            session, household_id=seed.household_id, product_id=product.id
        )

        assert first.id == second.id
        assert loaded == product
        assert len(documents) == 1
        assert (
            session.query(KnowledgeDocument)
            .filter(KnowledgeDocument.product_id == product.id)
            .count()
            == 1
        )
        facts = (
            session.query(KnowledgeFact)
            .filter(KnowledgeFact.document_id == first.id)
            .all()
        )
        assert {fact.fact_type for fact in facts} == {"brand", "nutrition"}
        assert all(fact.confirmation_status == "confirmed" for fact in facts)
        session.close()
