from __future__ import annotations

import asyncio

from app.answer_service import AnswerService
from app.compat import build_answer_rag
from app.config import get_settings
from app.dialogue_state import DialogueManager, DialogueState


async def main() -> None:
    settings = get_settings()
    rag = build_answer_rag(settings.docs_dir)
    service = AnswerService(rag, settings)

    print("Support RAG Bot — CLI проверка")
    print(f"Документов/фрагментов загружено: {len(rag.chunks)}")
    print("Напиши вопрос или exit для выхода.\n")

    manager, state = DialogueManager(), DialogueState()
    turn = 0
    while True:
        question = input("Ты: ").strip()
        if question.lower() in {"exit", "quit", "выход"}:
            break
        turn += 1
        state = manager.advance(state, question, turn)
        answer = await service.answer(question, state=state)
        print("\nБот:\n" + answer.text + "\n")
        state = manager.observe_answer(state, scenario=answer.scenario, reason=answer.scenario_reason,
                                       question=answer.text, slot=answer.clarification_slot)


if __name__ == "__main__":
    asyncio.run(main())
