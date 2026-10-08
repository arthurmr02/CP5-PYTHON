"""API REST (FastAPI) sobre os livros coletados da Open Library."""
import re
from pathlib import Path
from typing import Optional

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from database.conexao import obter_colecao

app = FastAPI(
    title="API Open Library - Projeto Universitário",
    description="Consulta de livros coletados da Open Library pelo crawler.",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def col():
    return obter_colecao()


def serializar(doc):
    doc["id"] = str(doc.pop("_id"))
    for k in ("coletado_em", "primeira_coleta_em"):
        if doc.get(k):
            doc[k] = doc[k].isoformat()
    return doc


def montar_filtro(titulo=None, autor=None, assunto=None, idioma=None, ano_min=None, ano_max=None, q=None):
    f = {}
    rx = lambda s: {"$regex": re.escape(s), "$options": "i"}
    if titulo:
        f["titulo"] = rx(titulo)
    if autor:
        f["autores"] = rx(autor)
    if assunto:
        f["assuntos"] = rx(assunto)
    if idioma:
        f["idiomas"] = idioma.lower()
    if ano_min is not None or ano_max is not None:
        f["ano_primeira_publicacao"] = {}
        if ano_min is not None:
            f["ano_primeira_publicacao"]["$gte"] = ano_min
        if ano_max is not None:
            f["ano_primeira_publicacao"]["$lte"] = ano_max
    if q:
        f["$or"] = [{"titulo": rx(q)}, {"autores": rx(q)}, {"assuntos": rx(q)}]
    return f


ORDENACOES = {"titulo", "ano_primeira_publicacao", "qtd_edicoes", "avaliacao_media", "coletado_em"}


@app.get("/", include_in_schema=False)
def raiz():
    return RedirectResponse("/dashboard/")


@app.get("/api/saude", tags=["Geral"], summary="Verifica a API e o banco")
def saude():
    return {"status": "ok", "registros": col().count_documents({})}


@app.get("/api/livros", tags=["Livros"], summary="Lista livros com paginação e filtros")
def listar_livros(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    titulo: Optional[str] = None,
    autor: Optional[str] = None,
    assunto: Optional[str] = None,
    idioma: Optional[str] = None,
    ano_min: Optional[int] = None,
    ano_max: Optional[int] = None,
    q: Optional[str] = Query(None, description="Busca livre em título, autor e assunto"),
    ordenar: str = Query("titulo", description=f"Campo: {', '.join(sorted(ORDENACOES))}"),
    ordem: str = Query("asc", pattern="^(asc|desc)$"),
):
    if ordenar not in ORDENACOES:
        raise HTTPException(400, "Campo de ordenação inválido")
    f = montar_filtro(titulo, autor, assunto, idioma, ano_min, ano_max, q)
    total = col().count_documents(f)
    cur = (col().find(f).sort(ordenar, 1 if ordem == "asc" else -1)
           .skip((pagina - 1) * por_pagina).limit(por_pagina))
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina,
            "total_paginas": (total + por_pagina - 1) // por_pagina,
            "itens": [serializar(d) for d in cur]}


@app.get("/api/livros/chave/{olid}", tags=["Livros"], summary="Busca livro pela chave da obra (ex.: OL45804W)")
def livro_por_chave(olid: str):
    doc = col().find_one({"chave": f"/works/{olid}"})
    if not doc:
        raise HTTPException(404, "Livro não encontrado")
    return serializar(doc)


@app.get("/api/livros/{id}", tags=["Livros"], summary="Busca livro pelo id do MongoDB")
def livro_por_id(id: str):
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "Id inválido")
    doc = col().find_one({"_id": ObjectId(id)})
    if not doc:
        raise HTTPException(404, "Livro não encontrado")
    return serializar(doc)


def _top(campo, limite):
    return [{"nome": d["_id"], "total": d["total"]} for d in col().aggregate([
        {"$unwind": f"${campo}"}, {"$group": {"_id": f"${campo}", "total": {"$sum": 1}}},
        {"$sort": {"total": -1, "_id": 1}}, {"$limit": limite}])]


@app.get("/api/estatisticas", tags=["Estatísticas"], summary="Indicadores gerais")
def estatisticas():
    c = col()
    g = list(c.aggregate([{"$group": {
        "_id": None, "total": {"$sum": 1},
        "media_ano": {"$avg": "$ano_primeira_publicacao"},
        "media_edicoes": {"$avg": "$qtd_edicoes"},
        "media_avaliacao": {"$avg": "$avaliacao_media"},
        "ano_min": {"$min": "$ano_primeira_publicacao"},
        "ano_max": {"$max": "$ano_primeira_publicacao"},
        "ultima_coleta": {"$max": "$coletado_em"}}}]))
    g = g[0] if g else {}
    autores = list(c.aggregate([{"$unwind": "$autores"}, {"$group": {"_id": "$autores"}}, {"$count": "n"}]))
    r = lambda v, n=1: round(v, n) if v is not None else None
    return {
        "total_livros": g.get("total", 0),
        "autores_unicos": autores[0]["n"] if autores else 0,
        "media_ano_publicacao": r(g.get("media_ano")),
        "media_edicoes": r(g.get("media_edicoes")),
        "media_avaliacao": r(g.get("media_avaliacao"), 2),
        "ano_mais_antigo": g.get("ano_min"),
        "ano_mais_recente": g.get("ano_max"),
        "ultima_coleta": g["ultima_coleta"].isoformat() if g.get("ultima_coleta") else None,
        "com_avaliacao": c.count_documents({"avaliacao_media": {"$ne": None}}),
    }


@app.get("/api/estatisticas/autores", tags=["Estatísticas"], summary="Autores com mais livros")
def top_autores(limite: int = Query(10, ge=1, le=50)):
    return _top("autores", limite)


@app.get("/api/estatisticas/assuntos", tags=["Estatísticas"], summary="Assuntos mais frequentes")
def top_assuntos(limite: int = Query(10, ge=1, le=50)):
    return _top("assuntos", limite)


@app.get("/api/estatisticas/idiomas", tags=["Estatísticas"], summary="Livros por idioma")
def por_idioma(limite: int = Query(10, ge=1, le=50)):
    return _top("idiomas", limite)


@app.get("/api/estatisticas/assuntos-buscados", tags=["Estatísticas"], summary="Livros por assunto coletado")
def por_assunto_buscado():
    return _top("assuntos_buscados", 50)


@app.get("/api/estatisticas/decadas", tags=["Estatísticas"], summary="Livros por década de 1ª publicação")
def por_decada(desde: int = Query(1800, description="Décadas anteriores são agrupadas")):
    res = col().aggregate([
        {"$match": {"ano_primeira_publicacao": {"$ne": None}}},
        {"$project": {"d": {"$max": [desde - 10, {"$subtract": ["$ano_primeira_publicacao",
                                                               {"$mod": ["$ano_primeira_publicacao", 10]}]}]}}},
        {"$group": {"_id": "$d", "total": {"$sum": 1}}}, {"$sort": {"_id": 1}}])
    return [{"decada": f"< {desde}" if d["_id"] < desde else f"{d['_id']}s", "total": d["total"]} for d in res]


# Dashboard estático (consome apenas a API via fetch)
_dash = Path(__file__).resolve().parent.parent / "dashboard"
app.mount("/dashboard", StaticFiles(directory=_dash, html=True), name="dashboard")
