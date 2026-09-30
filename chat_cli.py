from langchain_core.messages import HumanMessage
from rag.graph import graph

config = {"configurable": {"thread_id": "cli-session"}}

while True:
    question = input("\nYou: ").strip()
    if question.lower() in {"exit", "quit"}:
        break
    result = graph.invoke({"messages": [HumanMessage(question)]}, config)
    print(f"  query: {result['search_query']!r}  attempts: {result['attempts']}")
    for d in result["documents"]:
        print(f"  [{d['rerank_score']:.2f}] {d['source']} p{d['page']}")
    print("\nBot:", result["messages"][-1].content)
