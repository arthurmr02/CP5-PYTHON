"""Módulo de persistência: conexão com o MongoDB e operações de gravação."""
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient, UpdateOne

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "openlibrary")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "livros")

_cliente = None


def obter_colecao():
    """Retorna a coleção de livros, criando os índices necessários."""
    global _cliente
    if _cliente is None:
        _cliente = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, tz_aware=True)
    col = _cliente[MONGO_DB][MONGO_COLLECTION]
    criar_indices(col)
    return col


def criar_indices(col):
    """Índice único na chave da obra (evita duplicatas) e índices de consulta."""
    col.create_index([("chave", ASCENDING)], unique=True, name="uk_chave")
    col.create_index([("titulo", ASCENDING)])
    col.create_index([("autores", ASCENDING)])
    col.create_index([("assuntos", ASCENDING)])
    col.create_index([("ano_primeira_publicacao", ASCENDING)])


def salvar_livros(col, livros):
    """Faz upsert dos livros pela chave. Nunca apaga dados anteriores.

    O campo `assuntos_buscados` acumula (via $addToSet) os assuntos pelos
    quais a obra foi encontrada; `primeira_coleta_em` é gravado só na inserção.
    Retorna (inseridos, atualizados).
    """
    if not livros:
        return 0, 0
    ops = []
    for livro in livros:
        doc = dict(livro)
        assunto = doc.pop("assunto_buscado", None)
        update = {
            "$set": doc,
            "$setOnInsert": {"primeira_coleta_em": datetime.now(timezone.utc)},
        }
        if assunto:
            update["$addToSet"] = {"assuntos_buscados": assunto}
        ops.append(UpdateOne({"chave": doc["chave"]}, update, upsert=True))
    res = col.bulk_write(ops, ordered=False)
    return res.upserted_count, res.modified_count
