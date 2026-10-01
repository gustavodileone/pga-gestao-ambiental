#!/usr/bin/env python3
"""Conta visualizações da homepage por website e por dia a partir de um access.log
no formato JSON (uma entrada por linha, gerado pelo nginx).

Uma "visualização" é qualquer requisição à raiz do site ("/", "/index.php" ou
"/index.html", com ou sem query string), sem filtrar método, status ou
user agent. Arquivos, páginas internas, ajax e API não entram. Subdomínios
(mail.site.com.br, marketing.site.com.br etc.) também são ignorados; apenas o
domínio principal e sua variante www. são contados.

O relatório é impresso no terminal e salvo, junto com um CSV, na pasta data/
(data/visualizacoes.txt e .csv).

Uso:
    python3 visualizacoes.py [access.log] [--manter-www] [--dados data]
"""

import argparse
import csv
import ipaddress
import json
import re
import sys
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# Pasta onde os scripts gravam relatórios, CSVs e o cache do Website Carbon.
PASTA_DADOS = Path(__file__).resolve().with_name("data")

HOMEPAGE = re.compile(r"^/(index\.(php|html?))?$", re.IGNORECASE)
# Segundos níveis usados sob TLDs de país (ex.: .com.br, .com.py, .net.ar).
SEGUNDO_NIVEL = {"com", "net", "org", "gov", "edu", "mil", "art", "blog",
                 "eng", "ind", "adv", "med", "tur", "co", "ac"}


def normalizar_host(host, manter_www):
    host = (host or "").strip().lower().rstrip(".")
    host = host.split(":", 1)[0]
    if not manter_www and host.startswith("www."):
        host = host[4:]
    return host


def eh_subdominio(host):
    rotulos = host.split(".")
    if rotulos[0] == "www" and len(rotulos) > 1:
        rotulos = rotulos[1:]
    tamanho_base = 2
    if len(rotulos[-1]) == 2 and len(rotulos) >= 3 and rotulos[-2] in SEGUNDO_NIVEL:
        tamanho_base = 3
    return len(rotulos) > tamanho_base


def eh_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def eh_homepage(entrada):
    partes = entrada.get("request", "").split(" ")
    if len(partes) < 2:
        return False
    caminho = partes[1].split("?", 1)[0].split("#", 1)[0]
    return bool(HOMEPAGE.match(caminho))


def entradas(caminho_log, manter_www):
    """Percorre o log e produz (host, dia, entrada) dos domínios principais."""
    invalidas = 0
    with open(caminho_log, encoding="utf-8", errors="replace") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            try:
                entrada = json.loads(linha)
                dia = datetime.strptime(
                    entrada["time_local"], "%d/%b/%Y:%H:%M:%S %z"
                ).date()
            except (ValueError, KeyError):
                invalidas += 1
                continue

            host = normalizar_host(entrada.get("host"), manter_www=True)
            if not host or eh_ip(host) or eh_subdominio(host):
                continue
            if not manter_www and host.startswith("www."):
                host = host[4:]
            yield host, dia, entrada

    if invalidas:
        print(f"Aviso: {invalidas} linhas inválidas ignoradas.", file=sys.stderr)


def contar(caminho_log, manter_www):
    contagem = defaultdict(lambda: defaultdict(int))
    for host, dia, entrada in entradas(caminho_log, manter_www):
        if eh_homepage(entrada):
            contagem[host][dia] += 1
    return contagem


class _Duplicador:
    """Stream que repassa o que recebe para vários outros."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, texto):
        for stream in self.streams:
            stream.write(texto)

    def flush(self):
        for stream in self.streams:
            stream.flush()


@contextmanager
def espelhar_stdout(destino):
    """Enquanto ativo, tudo o que for impresso no stdout também vai para `destino`."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    original = sys.stdout
    with open(destino, "w", encoding="utf-8") as arquivo:
        sys.stdout = _Duplicador(original, arquivo)
        try:
            yield
        finally:
            sys.stdout = original
    print(f"Relatório salvo em {destino}", file=sys.stderr)


def imprimir(contagem):
    sites = sorted(contagem, key=lambda s: -sum(contagem[s].values()))
    for site in sites:
        dias = contagem[site]
        print(f"\n{site}  (total: {sum(dias.values())})")
        for dia in sorted(dias):
            print(f"  {dia:%d/%m/%Y}  {dias[dia]:>8}")


def salvar_csv(contagem, destino):
    with open(destino, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["site", "dia", "visualizacoes"])
        for site in sorted(contagem):
            for dia in sorted(contagem[site]):
                escritor.writerow([site, dia.isoformat(), contagem[site][dia]])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", nargs="?", default="access.log")
    parser.add_argument("--manter-www", action="store_true",
                        help="não agrupa www.site.com com site.com")
    parser.add_argument("--dados", type=Path, default=PASTA_DADOS,
                        help="pasta onde salvar relatório e CSV (padrão: data/)")
    args = parser.parse_args()

    with espelhar_stdout(args.dados / "visualizacoes.txt"):
        contagem = contar(args.log, args.manter_www)
        imprimir(contagem)
        salvar_csv(contagem, args.dados / "visualizacoes.csv")
    print(f"CSV salvo em {args.dados / 'visualizacoes.csv'}", file=sys.stderr)

if __name__ == "__main__":
    main()
