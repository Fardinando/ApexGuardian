from typing import Optional


async def search_error(query: str, max_results: int = 5) -> str:
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                results.append(f"Title: {r.get('title', '')}\nLink: {r.get('href', '')}\nSnippet: {r.get('body', '')}\n")
        return "\n---\n".join(results) if results else "Nenhum resultado encontrado."
    except ImportError:
        return "Biblioteca duckduckgo_search não disponível."
    except Exception as e:
        return f"Erro na pesquisa: {str(e)}"
