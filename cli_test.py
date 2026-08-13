from __future__ import annotations

import asyncio

from app.answer_service import AnswerService
from app.config import get_settings
from app.rag import SimpleRAG


async def main() -> None:
    settings = get_settings()
    rag = SimpleRAG(settings.docs_dir)
    service = AnswerService(rag, settings)

    print("Support RAG Bot — CLI проверка")
    print(f"Документов/фрагментов загружено: {len(rag.chunks)}")
    print("Напиши вопрос или exit для выхода.\n")

    history = []
    while True:
        question = input("Ты: ").strip()
        if question.lower() in {"exit", "quit", "выход"}:
            break
        answer = await service.answer(question, history=history)
        print("\nБот:\n" + answer.text + "\n")
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer.text[:1200]})
        history = history[-8:]


if __name__ == "__main__":
    asyncio.run(main())
