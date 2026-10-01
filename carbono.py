#!/usr/bin/env python3
"""Roda um teste no Website Carbon para uma URL qualquer, segue o link do
relatório devolvido e extrai os valores dos elementos span.js-countup-content.

Antes de cada teste a homepage do Website Carbon é carregada: a resposta traz
os cookies da Cloudflare (__cf_bm, cf_clearance), que ficam na sessão, e o
nonce do formulário ("run_test_nonce":"..."), extraído do HTML por regex.

No HTML servido, o conteúdo de span.js-countup-content é só um placeholder
("0", "0.0") que o JavaScript anima até o valor real, guardado no atributo
data-count do span.js-countup pai. Por isso o valor retornado vem de data-count
(e, na falta dele, do texto do próprio span).

Uso:
    python3 carbono.py https://exemplo.org
"""

import argparse
import re
import sys
import time

import requests

HOMEPAGE_URL = "https://www.websitecarbon.com/"
AJAX_URL = "https://www.websitecarbon.com/wp-admin/admin-ajax.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:156.0) Gecko/20100101 Firefox/156.0",
    "Accept": "*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.websitecarbon.com/",
    "Origin": "https://www.websitecarbon.com",
    "Sec-GPC": "1",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Priority": "u=4",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}

# Requisição de navegação à homepage: devolve o HTML com o nonce e faz a
# Cloudflare definir os cookies (__cf_bm, cf_clearance) na sessão.
HEADERS_HOMEPAGE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# ..."run_test_nonce":"9d1eb01b73"...
NONCE = re.compile(r'"run_test_nonce"\s*:\s*"([^"]+)"')

# <span class="js-countup" ... data-count="61" ...> <span class="js-countup-content">0</span>
COUNTUP = re.compile(
    r'<span\b(?P<pai>[^>]*\bclass="[^"]*\bjs-countup\b[^"]*"[^>]*)>\s*'
    r'<span\b[^>]*\bclass="[^"]*\bjs-countup-content\b[^"]*"[^>]*>(?P<texto>[^<]*)</span>',
    re.IGNORECASE,
)
DATA_COUNT = re.compile(r'\bdata-count="([^"]*)"', re.IGNORECASE)


def nova_sessao():
    sessao = requests.Session()
    sessao.headers.update(HEADERS)
    return sessao


def obter_nonce(sessao):
    """Abre a homepage do Website Carbon, o que deixa os cookies da Cloudflare
    na sessão, e devolve o nonce do formulário de teste encontrado no HTML."""
    # O parâmetro único fura o cache de página do site, que serve um HTML antigo
    # com nonce já expirado ({"error":"Invalid nonce."}).
    resp = sessao.get(HOMEPAGE_URL, params={"nc": time.time_ns()},
                      headers=HEADERS_HOMEPAGE, timeout=60)
    resp.raise_for_status()
    m = NONCE.search(resp.text)
    if not m:
        raise RuntimeError(f"run_test_nonce não encontrado em {HOMEPAGE_URL}")
    return m.group(1)


def rodar_teste(sessao, url, nonce):
    """Dispara o teste e devolve a URL do relatório."""
    # (None, valor) faz o requests montar campos multipart/form-data sem arquivo.
    campos = {
        "wgd-cc-url": (None, url),
        "action": (None, "run_new_test"),
        "wgd-cc-run-test-nonce": (None, nonce),
    }
    resp = sessao.post(AJAX_URL, files=campos, timeout=120)
    resp.raise_for_status()
    dados = resp.json()
    if not dados.get("success") or not dados.get("url"):
        raise RuntimeError(f"resposta inesperada do servidor: {resp.text}")
    return dados["url"]


def extrair_valores(html):
    valores = []
    for m in COUNTUP.finditer(html):
        data_count = DATA_COUNT.search(m.group("pai"))
        valores.append(data_count.group(1) if data_count else m.group("texto").strip())
    return valores


def emissao_por_visita(url, sessao=None):
    """Roda o teste para `url` e devolve (gramas de CO2 por visita, URL do relatório).
    Antes de cada teste a homepage é recarregada para renovar cookies e nonce."""
    propria = sessao is None
    if propria:
        sessao = nova_sessao()
    try:
        nonce = obter_nonce(sessao)
        url_relatorio = rodar_teste(sessao, url, nonce)
        resp = sessao.get(url_relatorio, timeout=120)
        resp.raise_for_status()
    finally:
        if propria:
            sessao.close()

    for m in COUNTUP.finditer(resp.text):
        if 'id="js-emission-count"' in m.group("pai"):
            data_count = DATA_COUNT.search(m.group("pai"))
            return float(data_count.group(1)), url_relatorio
    raise RuntimeError(f"emissão por visita não encontrada em {url_relatorio}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="URL a ser testada, ex.: https://exemplo.org")
    args = parser.parse_args()

    with nova_sessao() as sessao:
        nonce = obter_nonce(sessao)
        url_relatorio = rodar_teste(sessao, args.url, nonce)
        print(f"relatório: {url_relatorio}", file=sys.stderr)

        resp = sessao.get(url_relatorio, timeout=120)
        resp.raise_for_status()

    valores = extrair_valores(resp.text)
    if not valores:
        sys.exit("nenhum span.js-countup-content encontrado no relatório")
    for valor in valores:
        print(valor)


if __name__ == "__main__":
    main()
