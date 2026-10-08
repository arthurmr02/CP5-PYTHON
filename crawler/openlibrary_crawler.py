"""Web Crawler da Open Library (independente da API).

Uso:
    python -m crawler.openlibrary_crawler --assuntos fiction science --paginas 2 --limite 50
"""
import argparse
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from database.conexao import obter_colecao, salvar_livros

load_dotenv()

BASE_URL = "https://openlibrary.org"
URL_BUSCA = BASE_URL + "/search.json"
USER_AGENT = "OpenLibraryProjetoUniversitario/1.0 (projeto academico; contato: estudante@example.com)"
CAMPOS = ",".join([
    "key", "title", "author_name", "first_publish_year", "subject", "language",
    "edition_count", "ratings_average", "ratings_count", "cover_i", "publisher",
    "number_of_pages_median",
])
ASSUNTOS_PADRAO = ["fiction", "science", "history", "fantasy", "romance", "programming"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("crawler")


def limpar_texto(valor):
    """Remove espaços extras e caracteres de controle."""
    if not isinstance(valor, str):
        return None
    valor = re.sub(r"\s+", " ", valor).strip()
    return valor or None


def limpar_lista(valores, maximo=None, minusculo=False):
    """Normaliza lista de strings: limpa, remove vazios e duplicatas (mantém ordem)."""
    vistos, saida = set(), []
    for v in valores or []:
        v = limpar_texto(v)
        if not v:
            continue
        if minusculo:
            v = v.lower()
        chave = v.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(v)
    return saida[:maximo] if maximo else saida


def normalizar(doc, assunto, fonte_url):
    """Transforma um item bruto do search.json no documento do banco."""
    chave = doc.get("key")
    titulo = limpar_texto(doc.get("title"))
    if not chave or not titulo:
        return None
    ano = doc.get("first_publish_year")
    if not isinstance(ano, int) or ano < 1 or ano > datetime.now().year:
        ano = None
    nota = doc.get("ratings_average")
    capa = doc.get("cover_i")
    return {
        "chave": chave,  # ex.: /works/OL45804W
        "titulo": titulo,
        "autores": limpar_lista(doc.get("author_name")),
        "ano_primeira_publicacao": ano,
        "assuntos": limpar_lista(doc.get("subject"), maximo=25, minusculo=True),
        "idiomas": limpar_lista(doc.get("language"), minusculo=True),
        "editoras": limpar_lista(doc.get("publisher"), maximo=10),
        "qtd_edicoes": int(doc.get("edition_count") or 0),
        "paginas_mediana": doc.get("number_of_pages_median"),
        "avaliacao_media": round(float(nota), 2) if nota is not None else None,
        "qtd_avaliacoes": int(doc.get("ratings_count") or 0),
        "capa_id": capa,
        "capa_url": f"https://covers.openlibrary.org/b/id/{capa}-M.jpg" if capa else None,
        "url": BASE_URL + chave,
        "fonte_url": fonte_url,
        "origem": "openlibrary.org",
        "assunto_buscado": assunto,
        "coletado_em": datetime.now(timezone.utc),
    }


def buscar_pagina(sessao, assunto, pagina, limite, tentativas=3):
    """Baixa uma página de resultados (com novas tentativas em caso de erro)."""
    params = {"subject": assunto, "page": pagina, "limit": limite, "fields": CAMPOS}
    for t in range(1, tentativas + 1):
        try:
            r = sessao.get(URL_BUSCA, params=params, timeout=30)
            r.raise_for_status()
            return r.json(), r.url
        except requests.RequestException as e:
            log.warning("Erro em %s pág. %s (tentativa %s): %s", assunto, pagina, t, e)
            time.sleep(3 * t)
    return None, None


def executar(assuntos, paginas, limite, atraso):
    col = obter_colecao()
    sessao = requests.Session()
    sessao.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    total_ins = total_atu = total_lidos = 0
    for assunto in assuntos:
        for pagina in range(1, paginas + 1):
            dados, url = buscar_pagina(sessao, assunto, pagina, limite)
            if not dados:
                break
            itens = dados.get("docs", [])
            livros = [l for l in (normalizar(d, assunto, url) for d in itens) if l]
            ins, atu = salvar_livros(col, livros)
            total_ins += ins
            total_atu += atu
            total_lidos += len(livros)
            log.info("%s pág. %s: %s lidos, %s novos, %s atualizados", assunto, pagina, len(livros), ins, atu)
            if len(itens) < limite:
                break
            time.sleep(atraso)  # educação com o servidor
        time.sleep(atraso)
    log.info("Fim: %s lidos, %s novos, %s atualizados. Total no banco: %s",
             total_lidos, total_ins, total_atu, col.count_documents({}))


def main():
    p = argparse.ArgumentParser(description="Crawler de livros da Open Library")
    p.add_argument("--assuntos", nargs="+", default=ASSUNTOS_PADRAO, help="Assuntos (subjects) a coletar")
    p.add_argument("--paginas", type=int, default=2, help="Páginas por assunto")
    p.add_argument("--limite", type=int, default=50, help="Itens por página (máx. 100)")
    p.add_argument("--atraso", type=float, default=float(os.getenv("CRAWLER_DELAY", "1.5")),
                   help="Segundos entre requisições")
    a = p.parse_args()
    executar(a.assuntos, a.paginas, min(a.limite, 100), a.atraso)


if __name__ == "__main__":
    main()
