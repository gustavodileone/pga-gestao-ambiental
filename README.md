# Pegada de carbono dos sites hospedados

Estimativa do CO₂ emitido pelas visitas aos sites que uma empresa hospeda, calculada a partir do log de acesso do servidor web.

## Contexto e intuito

Este projeto foi feito para a disciplina de **Gestão Ambiental** e é uma das
partes de um trabalho maior: a elaboração de um **PGA (Programa de Gestão
Ambiental)** para uma empresa real.

O código em si foi vibecodado utilizando o *Claude Code*, visando a agilidade no MVP.

O objetivo aqui é transformar esse impacto, que costuma ser invisível, num
número de massa de CO₂. Com ele, o PGA pode:

- ter uma **linha de base** das emissões dos sites hospedados;
- identificar **quais sites mais emitem** e onde otimizar primeiro
  (imagens, scripts, tamanho das páginas);
- definir **metas e indicadores** e medir de novo depois das melhorias.

## O que é calculado

Para cada site hospedado no servidor, no período coberto pelo log:

```
emissão = visualizações × gramas de CO₂ por visita
```

- **Visualizações** vêm do `access.log` do *nginx* do servidor.
- **Gramas de CO₂ por visita** vêm do [Website Carbon](https://www.websitecarbon.com/),
  que testa a página e estima a emissão de uma visita.

Saídas principais: emissão por site, total do período e média por dia.

## Metodologia

### 1. Contagem de visualizações (`visualizacoes.py`)

O log está em JSON, uma requisição por linha:

```json
{
  "time_local":"14/Sep/2026:15:32:57 +0000",
  "remote_addr":"...",
  "host":"exemplo.com.br",
  "request":"GET /poeta/jalaladim-maome-rumi HTTP/1.1",
  "status":200,
  "body_bytes_sent":1,
  "http_referer":"",
  "http_user_agent":"..."
}
```

- Só entram **domínios principais** e sua variante `www.`. `www.site.com.br`
  e `site.com.br` são somados. Subdomínios (`mail.site.com.br`,
  `marketing.site.com.br`) e acessos por IP ficam de fora.
- No cálculo de emissões, hosts com menos de 10 visualizações
  (`--min-visualizacoes`) são descartados. Normalmente são
  cabeçalhos `Host` forjados por bots.

Contam-se apenas as requisições à raiz do site (`/`,
`/index.php`, `/index.html`). Não filtra método, status nem user agent.

### 2. Emissão por visita (`carbono.py`)

Para cada URL a medir, o script:

1. abre a homepage do Website Carbon, guarda os cookies definidos pela
   Cloudflare e extrai do HTML o *nonce* do formulário. Um parâmetro único na
   URL evita o cache de página do site, que serviria um nonce já expirado;
2. envia a URL para teste, como o formulário do site faria;
3. abre o relatório gerado e lê os **gramas de CO₂ por visita**.

O valor do Website Carbon estima **uma visita completa**: data center, rede de
transmissão e dispositivo do visitante, não só o servidor. Ele se baseia
principalmente no volume de dados transferidos pela página e em se a
hospedagem usa energia renovável.

Os resultados ficam em cache em `data/carbono_cache.json`, para não repetir o
teste da mesma URL a cada execução.

### 3. Cruzamento (`emissoes.py`)

Para cada site: visualizações da homepage × g/visita da homepage.

## Como rodar

### Requisitos

- Python 3 e a biblioteca `requests`:

  ```sh
  python3 -m pip install requests
  ```

- Um `access.log` do nginx no formato JSON acima
- Acesso à internet para consultar o Website Carbon.

### Executando tudo

São três scripts, rodados nesta ordem a partir da raiz do projeto.
`visualizacoes.py` e `emissoes.py` imprimem o resultado no terminal e também o
salvam em `data/`. `carbono.py` só imprime os valores do relatório da URL
testada.

```sh
# 1. Contagem de visualizações (só lê o log, sem rede)
python3 visualizacoes.py access.log                # → data/visualizacoes.*

# 2. Teste do Website Carbon com uma URL, para conferir o acesso antes do cálculo
python3 carbono.py https://exemplo.com.br

# 3. Emissões: testa as URLs no Website Carbon e cruza com as visualizações
python3 emissoes.py access.log                     # → data/emissoes.*
```

O passo 3 já faz a contagem internamente, então o relatório final sai só com
ele. Os passos 1 e 2 servem para conferir as visualizações e o acesso ao
Website Carbon. A primeira execução do passo 3 demora mais, porque testa cada
URL. As seguintes reaproveitam o cache.

O relatório final fica em `data/emissoes.txt`, com a tabela por site, o total do período e a
média por dia. Os dados para planilha ficam no `.csv` de mesmo nome.

### Opções

```sh
python3 visualizacoes.py [access.log] [--manter-www] [--dados data]
python3 emissoes.py [access.log] [--min-visualizacoes 10] \
    [--dados data] [--cache data/carbono_cache.json] [--sem-cache]
python3 carbono.py https://exemplo.com.br
```

- `--dados`: pasta onde salvar relatórios, CSVs e cache (padrão: `data/`).
- `--cache` / `--sem-cache`: outro arquivo de cache, ou refazer todos os testes
  sem gravar cache. Para forçar novos testes, também basta apagar
  `data/carbono_cache.json`.
- `--min-visualizacoes`: filtro descrito na metodologia.

### Saídas

Tudo é gravado em `data/`. O conteúdo da pasta é ignorado pelo git, pois são
resultados gerados a partir do log. Só a pasta vazia (`data/.gitkeep`) fica no
repositório.

| Arquivo em `data/` | Conteúdo |
|---|---|
| `emissoes.txt` | relatório por site: visualizações, g/visita, emissão; total e média diária |
| `emissoes.csv` | `site, visualizacoes, gramas_por_visita, gramas_total` |
| `visualizacoes.csv` / `.txt` | visualizações da homepage por site e dia |
| `carbono_cache.json` | medições do Website Carbon já feitas (g/visita e link do relatório) |

## Limitações

- **Tráfego de bots.** A contagem não filtra user agents, então parte das
  visualizações vem de robôs e crawlers.
- **Só a homepage.** Páginas internas não entram na conta, então a emissão
  real dos sites é maior que a estimada.
- **Cache do navegador.** O Website Carbon estima uma visita típica. Visitas
  repetidas, que reaproveitam arquivos em cache, gastam menos.
- **Localização do servidor.** A estimativa usa fatores médios de intensidade
  de carbono. Ela não reflete a matriz elétrica específica da região onde o
  servidor está.
- **Consumo fixo do servidor.** O servidor fica ligado mesmo sem visitas. Essa
  energia de base não é proporcional às visualizações e não entra nesta conta.
- **Dependência de serviço externo.** O Website Carbon pode mudar o site ou
  bloquear requisições automatizadas (Cloudflare). Nesse caso as URLs aparecem
  como "sem medição" no fim do relatório, e basta rodar de novo depois.