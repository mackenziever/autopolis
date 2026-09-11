import asyncio

from llm.cognitive_worker import CognitiveJob, CognitiveWorker


def test_cognitive_worker_processes_jobs():
    async def _run():
        calls = []

        async def fake_decide(**kwargs):
            calls.append(kwargs)
            return {"ok": True}

        worker = CognitiveWorker(fake_decide, maxsize=8).start()
        assert worker.submit_nowait(
            CognitiveJob("agent_001", 1, "reflect", ["a", "b"], "sys", {"x": 1})
        )
        await asyncio.sleep(0.05)
        await worker.stop()
        assert worker.stats["done"] == 1
        assert calls[0]["agent_id"] == "agent_001"

    asyncio.run(_run())
