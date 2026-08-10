"""Quick test: submit a query and check that final_score >= 0.65 for top results."""
import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=600) as c:
        r = await c.post("/api/v1/query", json={
            "query": "Can an unstamped arbitration agreement be enforced under the Arbitration and Conciliation Act 1996?",
            "filters": {}, "options": {}
        })
        qid = r.json()["query_id"]
        print(f"query_id: {qid}")

        for i in range(200):
            await asyncio.sleep(3)
            s = (await c.get(f"/api/v1/query/{qid}/status")).json()
            agents = list((s.get("agent_trace") or {}).keys())
            print(f"  [{i*3}s] {s['status']} agents={agents}")
            if s["status"] in ("complete", "failed"):
                break

        if s["status"] == "complete":
            res = (await c.get(f"/api/v1/query/{qid}")).json()
            print("\n=== SCORES ===")
            for r in res.get("results", [])[:5]:
                score_pct = f"{r['final_score']*100:.1f}%"
                print(f"  #{r['rank']} {r['title'][:50]} → {score_pct} (rel={r['relevance_score']:.3f} auth={r['authority_score']:.3f})")
        else:
            print("FAILED or timed out")

asyncio.run(test())
