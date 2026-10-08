// Dashboard: todos os dados vêm exclusivamente da API REST (fetch).
// Se aberto por outro servidor estático, ajuste API_BASE (ex.: http://localhost:8000).
const API_BASE = window.API_BASE || (location.port === "8000" ? "" : "http://localhost:8000");
let paginaAtual = 1, totalPaginas = 1;

async function api(caminho) {
  const r = await fetch(API_BASE + caminho);
  if (!r.ok) throw new Error(`Erro ${r.status} em ${caminho}`);
  return r.json();
}
const fmt = (v, d = 0) => v == null ? "–" : Number(v).toLocaleString("pt-BR", { maximumFractionDigits: d });

function grafico(id, tipo, rotulos, valores, cor, horizontal = false) {
  new Chart(document.getElementById(id), {
    type: tipo,
    data: { labels: rotulos, datasets: [{ label: "Livros", data: valores, backgroundColor: cor }] },
    options: { indexAxis: horizontal ? "y" : "x", plugins: { legend: { display: tipo === "doughnut" } }, animation: false },
  });
}

async function carregarIndicadores() {
  const e = await api("/api/estatisticas");
  document.getElementById("c-total").textContent = fmt(e.total_livros);
  document.getElementById("c-autores").textContent = fmt(e.autores_unicos);
  document.getElementById("c-ano").textContent = e.media_ano_publicacao ? Math.round(e.media_ano_publicacao) : "–";
  document.getElementById("c-edicoes").textContent = fmt(e.media_edicoes, 1);
  document.getElementById("c-nota").textContent = e.media_avaliacao ? fmt(e.media_avaliacao, 2) + " ★" : "–";
}

async function carregarGraficos() {
  const [dec, ass, aut, idi] = await Promise.all([
    api("/api/estatisticas/decadas?desde=1900"), api("/api/estatisticas/assuntos?limite=10"),
    api("/api/estatisticas/autores?limite=10"), api("/api/estatisticas/idiomas?limite=8")]);
  grafico("g-decadas", "bar", dec.map(d => d.decada), dec.map(d => d.total), "#4c6ef5");
  grafico("g-assuntos", "bar", ass.map(d => d.nome), ass.map(d => d.total), "#20c997", true);
  grafico("g-autores", "bar", aut.map(d => d.nome), aut.map(d => d.total), "#f59f00", true);
  grafico("g-idiomas", "doughnut", idi.map(d => d.nome), idi.map(d => d.total),
    ["#4c6ef5", "#20c997", "#f59f00", "#e64980", "#7950f2", "#15aabf", "#82c91e", "#fd7e14"]);
}

function parametrosBusca() {
  const p = new URLSearchParams({ pagina: paginaAtual, por_pagina: 15 });
  const campos = { titulo: "f-titulo", autor: "f-autor", assunto: "f-assunto", ano_min: "f-ano-min", ano_max: "f-ano-max" };
  for (const [k, id] of Object.entries(campos)) {
    const v = document.getElementById(id).value.trim();
    if (v) p.set(k, v);
  }
  const ord = document.getElementById("f-ordenar").value;
  p.set("ordenar", ord); p.set("ordem", ord === "titulo" ? "asc" : "desc");
  return p;
}

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function carregarTabela() {
  const r = await api("/api/livros?" + parametrosBusca());
  totalPaginas = Math.max(1, r.total_paginas);
  document.getElementById("info-resultados").textContent = `${fmt(r.total)} livro(s) encontrado(s).`;
  document.getElementById("tabela").innerHTML = r.itens.map(l => `<tr>
    <td>${l.capa_id ? `<img src="https://covers.openlibrary.org/b/id/${l.capa_id}-S.jpg" alt="capa">` : ""}</td>
    <td><a href="${esc(l.url)}" target="_blank">${esc(l.titulo)}</a></td>
    <td>${esc(l.autores.slice(0, 3).join(", "))}</td>
    <td>${l.ano_primeira_publicacao ?? "–"}</td><td>${l.qtd_edicoes}</td>
    <td>${l.avaliacao_media ? l.avaliacao_media.toFixed(2) + " (" + l.qtd_avaliacoes + ")" : "–"}</td>
    <td>${l.assuntos.slice(0, 4).map(a => `<span class="tag">${esc(a)}</span>`).join("")}</td></tr>`).join("");
  document.getElementById("pag").textContent = `Página ${paginaAtual} de ${totalPaginas}`;
  document.getElementById("ant").disabled = paginaAtual <= 1;
  document.getElementById("prox").disabled = paginaAtual >= totalPaginas;
}

document.getElementById("form-busca").addEventListener("submit", e => { e.preventDefault(); paginaAtual = 1; carregarTabela(); });
document.getElementById("limpar").onclick = () => { document.getElementById("form-busca").reset(); paginaAtual = 1; carregarTabela(); };
document.getElementById("ant").onclick = () => { paginaAtual--; carregarTabela(); };
document.getElementById("prox").onclick = () => { paginaAtual++; carregarTabela(); };

Promise.all([carregarIndicadores(), carregarGraficos(), carregarTabela()])
  .catch(err => alert("Falha ao consultar a API: " + err.message));
