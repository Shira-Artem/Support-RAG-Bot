from pathlib import Path

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.api import create_app
from app.knowledge import DocumentLoader
from app.retrieval import Retriever
from app.vector_store import QdrantStore


class FakeEmbedding:
    dimension = 4

    def embed(self, texts):
        vectors = []
        for text in texts:
            lower = text.lower()
            vector = [float("фн" in lower), float("офд" in lower), float("касс" in lower or "печать" in lower or "печати" in lower or "атол" in lower), float("маркиров" in lower)]
            vectors.append(vector if any(vector) else [0.001, 0.001, 0.001, 0.001])
        return vectors


def make_store(tmp_path: Path):
    store = QdrantStore(QdrantClient(":memory:"), FakeEmbedding())
    def write(name, text, status="approved", model=None):
        (tmp_path / name).write_text(text, encoding="utf-8")
        (tmp_path / f"{name}.meta.yaml").write_text(f"status: {status}\ncategory: support\n" + ("verified_at: 2026-10-12\n" if status == "approved" else "") + (f"model: {model}\n" if model else ""), encoding="utf-8")
    write("234.txt", "Ошибка ФН 234. Проверьте настройки накопителя.")
    write("235.txt", "Ошибка ФН 235. Ресурс хранения исчерпан.")
    write("ofd.txt", "Не отправляются чеки в ОФД. Проверьте связь.")
    write("atol.txt", "АТОЛ 30Ф. Ошибка печати фискального документа.", model="АТОЛ 30Ф")
    write("atol31.txt", "АТОЛ 31Ф. Ошибка печати фискального документа.", model="АТОЛ 31Ф")
    write("draft.txt", "Секретная инструкция ЕГАИС.", status="draft")
    return store, write


def test_idempotence_update_and_remove(tmp_path: Path):
    store, write = make_store(tmp_path)
    docs = DocumentLoader(tmp_path).load_all()
    assert store.index(docs)["indexed"] == 6
    assert store.index(docs)["unchanged"] == 6
    original = len(store.all_points())
    write("234.txt", "Ошибка ФН 234. " + "Проверьте накопитель. " * 100)
    assert store.index(DocumentLoader(tmp_path).load_all())["indexed"] == 1
    assert len(store.all_points()) > original
    write("234.txt", "Ошибка ФН 234. Новая проверенная инструкция.")
    change = store.index(DocumentLoader(tmp_path).load_all())
    assert change["indexed"] == 1 and change["removed"] > 0
    assert len(store.all_points()) == original
    (tmp_path / "235.txt").unlink()
    assert store.index(DocumentLoader(tmp_path).load_all(), remove_missing=True)["removed"] >= 1
    assert not any(point.payload["source"] == "235.txt" for point in store.all_points())


def test_hybrid_exact_codes_filters_and_abstain(tmp_path: Path):
    store, _ = make_store(tmp_path)
    store.index(DocumentLoader(tmp_path).load_all())
    retriever = Retriever(store)
    hits = retriever.search("ФН 235")
    assert hits and all("235" in hit.text for hit in hits)
    assert retriever.search("АТОЛ 30Ф") and all(hit.metadata["model"] == "АТОЛ 30Ф" for hit in retriever.search("АТОЛ 30Ф"))
    assert retriever.search("касса не пробивает чек")
    assert retriever.search("ЕГАИС секретная") == []
    assert retriever.search("астрофизика квазар галактика") == []
    assert retriever.search("ФН 235", filters={"category": "other"}) == []
    assert Retriever(store, demo=True).search("ЕГАИС секретная")


def test_numbered_question_is_not_treated_as_exact_error_code(tmp_path: Path):
    store, _ = make_store(tmp_path)
    store.index(DocumentLoader(tmp_path).load_all())
    retriever = Retriever(store)
    assert retriever.search('1. Где ошибка ФН 235?')
    assert all('235' in hit.text for hit in retriever.search('1. Где ошибка ФН 235?'))
    assert retriever.search('запрос клиента: 2. Где посмотреть кассу АТОЛ?')


def test_semantic_result_without_lexical_overlap(tmp_path: Path):
    store = QdrantStore(QdrantClient(":memory:"), FakeEmbedding())
    (tmp_path / "printing.txt").write_text("Печать фискального документа не работает.", encoding="utf-8")
    (tmp_path / "printing.txt.meta.yaml").write_text("status: approved\nverified_at: 2026-10-12\n", encoding="utf-8")
    store.index(DocumentLoader(tmp_path).load_all())
    hit = Retriever(store).search("касса")[0]
    assert hit.lexical_score is None and hit.semantic_score is not None


def test_demo_error_codes_are_separate():
    store = QdrantStore(QdrantClient(":memory:"), FakeEmbedding())
    store.index(DocumentLoader(Path("data/docs")).load_all())
    hits = Retriever(store, demo=True).search("ФН 235")
    assert hits and all("Ошибка ФН 234" not in hit.text for hit in hits)


def test_evotor_models_do_not_mix(tmp_path: Path):
    store = QdrantStore(QdrantClient(":memory:"), FakeEmbedding())
    for name, model in [("six", "Эвотор 6"), ("lite", "Эвотор 6 lite"), ("seven2", "Эвотор 7.2"), ("seven3", "Эвотор 7.3")]:
        (tmp_path / f"{name}.txt").write_text(f"Модель {model}: проверьте питание кассы.", encoding="utf-8")
        (tmp_path / f"{name}.txt.meta.yaml").write_text(f"status: approved\nverified_at: 2026-10-12\nmodel: {model}\n", encoding="utf-8")
    store.index(DocumentLoader(tmp_path).load_all())
    retriever = Retriever(store)
    for model in ("Эвотор 6", "Эвотор 6 lite", "Эвотор 7.2", "Эвотор 7.3"):
        hits = retriever.search(model)
        assert hits and all(hit.metadata["model"] == model for hit in hits)


def test_named_manufacturer_does_not_return_other_vendor(tmp_path: Path):
    store = QdrantStore(QdrantClient(":memory:"), FakeEmbedding())
    for name, manufacturer in [("atol", "АТОЛ"), ("shtrih", "Штрих-М")]:
        (tmp_path / f"{name}.txt").write_text(f"ККТ {manufacturer} не передаёт чеки в ОФД.", encoding="utf-8")
        (tmp_path / f"{name}.txt.meta.yaml").write_text(
            f"status: approved\nverified_at: 2026-10-12\nmanufacturer: {manufacturer}\n", encoding="utf-8")
    store.index(DocumentLoader(tmp_path).load_all())
    retriever = Retriever(store)
    atol = retriever.search("АТОЛ не передаёт чеки")
    shtrih = retriever.search("Штрих-М не передаёт чеки")
    assert atol and all(hit.metadata["manufacturer"] == "АТОЛ" for hit in atol)
    assert shtrih and all(hit.metadata["manufacturer"] == "Штрих-М" for hit in shtrih)


def test_error_article_subsections_inherit_code_and_service_filter_runs_before_ranking(tmp_path):
    store = QdrantStore(QdrantClient(':memory:'), FakeEmbedding())
    folder = tmp_path / 'evotor'
    folder.mkdir()
    (folder / '235.md').write_text('---\ntitle: "Эвотор: ошибка ФН 235"\nstatus: approved\nverified_at: 2026-10-12\nmanufacturer: Эвотор\n---\n## Смысл\nПередача документов отсутствует более 30 дней.', encoding='utf-8')
    store.index(DocumentLoader(tmp_path).load_all())
    r = Retriever(store)
    hits = r.search('Эвотор ФН 235', source_prefixes=('evotor/',))
    assert hits and '30 дней' in hits[0].text
    assert r.search('Эвотор ФН 234', source_prefixes=('evotor/',)) == []
    assert r.search('Эвотор ФН 235', source_prefixes=('aqsi_online/',)) == []


def test_api_contract_and_validation(tmp_path: Path):
    store, _ = make_store(tmp_path)
    store.index(DocumentLoader(tmp_path).load_all())
    with TestClient(create_app(Retriever(store))) as client:
        data = client.post("/search", json={"query": "ФН 234", "top_k": 2}).json()
        assert data["results"] and data["results"][0]["metadata"]["source"] == "234.txt"
        assert "score" in data["results"][0]
        assert client.post("/search", json={"query": " "}).status_code == 422
        assert client.post("/search", json={"query": "ФН", "top_k": 50}).status_code == 422
        assert client.post("/search", json={"query": "ФН", "filters": {"status": "draft"}}).status_code == 422
