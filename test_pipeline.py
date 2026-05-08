import asyncio
import json
import httpx

async def test():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=300) as c:
        # Submit query
        r = await c.post("/api/v1/query", json={
            "query": "Can an unstamped arbitration agreement be enforced under the Arbitration and Conciliation Act 1996?",
            "filters": {},
            "options": {}
        })
        data = r.json()
        qid = data["query_id"]
        print("Submitted query_id:", qid)

        status = {}
        # Poll until complete or failed (max 6 minutes)
        for i in range(120):
            await asyncio.sleep(3)
            s = await c.get(f"/api/v1/query/{qid}/status")
            status = s.json()
            trace_keys = list((status.get("agent_trace") or {}).keys())
            elapsed = i * 3
            print(f"  [{elapsed}s] status={status['status']} agents_done={trace_keys}")
            if status["status"] in ("complete", "failed"):
                break

        print()
        if status["status"] == "complete":
            res = await c.get(f"/api/v1/query/{qid}")
            final = res.json()
            trace = final.get("agent_trace", {})
            print("=== PIPELINE RESULT ===")
            for agent, entry in trace.items():
                lat = entry.get("latency_ms", 0)
                lat_str = f"{lat/1000:.1f}s" if lat >= 1000 else f"{lat}ms"
                print(f"  {agent}: {entry.get('status','?')} ({lat_str})")
            print(f"  Results count: {len(final.get('results', []))}")
            if final.get("results"):
                top = final["results"][0]
                print(f"  Top result: {top.get('title','?')} [{top.get('year','?')}] score={top.get('final_score','?')}")
            if trace.get("debate"):
                debate_details = trace["debate"].get("details", {})
                rounds = debate_details.get("debate_rounds", [])
                print(f"  Debate rounds: {len(rounds)}")
                if rounds:
                    entries = rounds[0].get("entries", [])
                    print(f"  Debate entries in round 1: {len(entries)}")
                    if entries:
                        e = entries[0]
                        print(f"  Sample advocate arg: {str(e.get('advocate',{}).get('relevance_argument',''))[:120]}")
                rationale = debate_details.get("consensus_rationale", "")
                print(f"  Consensus rationale: {rationale[:200]}")
        else:
            print("Pipeline FAILED:", json.dumps(status, indent=2))

asyncio.run(test())
