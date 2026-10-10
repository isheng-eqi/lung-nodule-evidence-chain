import asyncio, json
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    async with streamablehttp_client("http://127.0.0.1:8020/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tl = await s.list_tools()
            names = [t.name for t in tl.tools]
            print(f"  ✅ MCP 会话建立 | 工具数 {len(names)}")
            print(f"  {names}")
            print()
            for desc in [
                "55岁男性，8mm混合磨玻璃结节，实性成分7mm，吸烟30年",
                "62岁男性，15mm混杂性磨玻璃结节，实性成分7mm，有毛刺征",
                "48岁女性，6mm纯磨玻璃结节，无吸烟史",
            ]:
                res = await s.call_tool("kg_consult_decision", {"description": desc})
                data = json.loads(res.content[0].text)
                dis = data.get("disambiguation") or []
                cd = data.get("cross_document") or {}
                print(f"  Q: {desc}")
                print(f"     条款 {data.get('clause')} | 跳数 {len(data.get('chain',[]))} | coverage {data.get('coverage')}")
                print(f"     消歧 {[d['rule_id'] for d in dis]} | 涉及文档 {cd.get('documents_involved')} 份 {[d['doc'] for d in cd.get('documents',[])]}")
                print()

asyncio.run(main())