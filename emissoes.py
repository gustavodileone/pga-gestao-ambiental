#!/usr/bin/env python3
"""Estima quanto CO2 os sites hospedados no servidor emitiram no período do
access.log, cruzando as visualizações contadas por visualizacoes.py com a
emissão por visita medida pelo Website Carbon via carbono.py.

    emissão = visualizações × gramas de CO2 por visita

Só a homepage de cada site entra na conta.

A emissão por visita do Website Carbon é a estimativa completa de uma visita
(data center, rede e dispositivo do visitante), não só a parcela do servidor.

O relatório é impresso no terminal e salvo, junto com um CSV, na pasta data/
(data/emissoes.txt e .csv). Os resultados do Website Carbon ficam em cache em
data/carbono_cache.json para não repetir o teste de cada URL a cada execução.

Uso:
    python3 emissoes.py [access.log] [--min-visualizacoes 10] [--dados data]
                        [--cache data/carbono_cache.json] [--sem-cache]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import requests

import carbono
import visualizacoes


def carregar_cache(caminho):
    try:
        return json.loads(Path(caminho).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def salvar_cache(caminho, cache):
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n")


def medir(sites, cache, caminho_cache):
    """Devolve {site: gramas por visita da homepage}; sites que falharem ficam de fora."""
    gramas = {}
    with carbono.nova_sessao() as sessao:
        for i, site in enumerate(sites, 1):
            if site in cache:
                gramas[site] = cache[site]["gramas_por_visita"]
                continue
            print(f"[{i}/{len(sites)}] testando {site}...", file=sys.stderr)
            try:
                valor, relatorio = carbono.emissao_por_visita(f"https://{site}", sessao=sessao)
            except (requests.RequestException, RuntimeError, ValueError) as erro:
                print(f"  falhou: {erro}", file=sys.stderr)
                continue
            gramas[site] = valor
            if caminho_cache:
                cache[site] = {"gramas_por_visita": valor, "relatorio": relatorio}
                salvar_cache(caminho_cache, cache)
    return gramas


def formatar_massa(gramas):
    return f"{gramas / 1000:.3f} kg" if gramas >= 1000 else f"{gramas:.2f} g"


def contar_visualizacoes(log, min_visualizacoes):
    """Devolve [(site, visualizações da homepage)] e os dias do log."""
    contagem = visualizacoes.contar(log, manter_www=False)
    dias = sorted({dia for d in contagem.values() for dia in d})
    linhas = []
    for site, por_dia in contagem.items():
        n = sum(por_dia.values())
        if "." in site and n >= min_visualizacoes:
            linhas.append((site, n))
    return linhas, dias


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", nargs="?", default="access.log")
    parser.add_argument("--min-visualizacoes", type=int, default=10,
                        help="ignora hosts com menos visualizações (Host forjado por bots)")
    parser.add_argument("--dados", type=Path, default=visualizacoes.PASTA_DADOS,
                        help="pasta onde salvar relatório e CSV (padrão: data/)")
    parser.add_argument("--cache", type=Path,
                        help="arquivo JSON com as medições já feitas "
                             "(padrão: carbono_cache.json dentro da pasta de dados)")
    parser.add_argument("--sem-cache", action="store_true",
                        help="refaz todos os testes e não grava cache")
    args = parser.parse_args()
    args.cache = args.cache or args.dados / "carbono_cache.json"

    with visualizacoes.espelhar_stdout(args.dados / "emissoes.txt"):
        gerar_relatorio(args, args.dados / "emissoes.csv")


def gerar_relatorio(args, destino_csv):
    linhas, dias = contar_visualizacoes(args.log, args.min_visualizacoes)

    # Testa primeiro os sites com mais visualizações.
    linhas.sort(key=lambda l: -l[1])
    caminho_cache = None if args.sem_cache else args.cache
    cache = {} if args.sem_cache else carregar_cache(args.cache)
    gramas = medir([site for site, _ in linhas], cache, caminho_cache)

    medidas = [(site, n, gramas[site]) for site, n in linhas if site in gramas]
    faltando = [site for site, _ in linhas if site not in gramas]
    medidas.sort(key=lambda m: -m[1] * m[2])

    print(f"\n{'site':<44} {'visualiz.':>10} {'g/visita':>9} {'emissão':>12}")
    for site, n, g in medidas:
        print(f"{site:<44} {n:>10} {g:>9.2f} {formatar_massa(n * g):>12}")

    total_geral = sum(n * g for _, n, g in medidas)
    total_views = sum(n for _, n, _ in medidas)
    print(f"\nTotal: {formatar_massa(total_geral)} de CO2 em {total_views} visualizações", end="")
    if dias:
        print(f" ({dias[0]:%d/%m/%Y} a {dias[-1]:%d/%m/%Y}, {len(dias)} dias;"
              f" média de {formatar_massa(total_geral / len(dias))}/dia)")
    else:
        print()

    if faltando:
        print(f"Aviso: sem medição para {len(faltando)} URL(s): {', '.join(faltando)}",
              file=sys.stderr)

    with open(destino_csv, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["site", "visualizacoes", "gramas_por_visita", "gramas_total"])
        for site, n, g in medidas:
            escritor.writerow([site, n, g, round(n * g, 4)])
    print(f"CSV salvo em {destino_csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
