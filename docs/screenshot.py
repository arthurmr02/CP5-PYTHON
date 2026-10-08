"""Gera docs/dashboard.png com Chromium headless (requer a API rodando na porta 8000)."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    nav = p.chromium.launch()
    pg = nav.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("dialog", lambda d: (erros.append(d.message), d.dismiss()))
    pg.goto("http://localhost:8000/dashboard/", wait_until="networkidle")
    pg.wait_for_selector("#tabela tr")
    pg.wait_for_timeout(1500)
    print("Total exibido:", pg.inner_text("#c-total"), "| linhas na tabela:", pg.locator("#tabela tr").count(), "| erros:", erros)
    pg.screenshot(path="docs/dashboard.png", full_page=True)
    nav.close()
