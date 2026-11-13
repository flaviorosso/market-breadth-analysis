# market-breadth-analysis

Statistical analysis of Market Breadth to identify tops and bottoms

## Global Market Breadth (dashboard + e-mail diário)

Breadth de tendência (% de ações acima da MA17) e de momentum (% com RSI14 acima de 65 ou abaixo de 35) para 9 mercados de ações, 43 países (via ETFs MSCI) e as maiores criptomoedas. O projeto gera um dashboard interativo e um e-mail diário às 8h (horário de Berlim), mesmo com o seu computador desligado.

### O que tem aqui

| Arquivo | Para que serve |
|---|---|
| `market_breadth.py` | Todo o projeto: coleta, cálculo, dashboard, gráfico e e-mail |
| `.github/workflows/daily.yml` | Agendamento diário no GitHub Actions (servidores do GitHub, de graça) |
| `requirements.txt` | Bibliotecas Python |
| `docs/` | Criado a cada execução: `index.html` (dashboard), `summary.png`, `history.csv`, `latest.csv` |

### O que mudou em relação ao notebook original

- **Uma função só** (`analyze`) para todos os mercados. Para incluir um mercado novo, basta adicionar uma linha em `MARKETS`.
- **Breadth sem distorção:** só entram no cálculo os ativos com dado válido no dia. Ticker sem dado não conta mais como "abaixo da média".
- **Tickers mortos** (deslistados ou renomeados) são detectados, ficam fora do cálculo e aparecem listados no dashboard. Assim você sabe o que atualizar.
- **RSI de Wilder**, o mesmo do TradingView e das outras plataformas.
- **Preços ajustados** por dividendos e desdobramentos (`auto_adjust=True`).
- **Limites relativos:** além dos limites fixos de 90% e 10%, cada mercado tem a sua faixa normal (percentis 5 e 95 dos últimos 5 anos).
- **Estudo de eventos:** mostra o retorno médio do índice 5, 20 e 60 dias depois que o breadth cruzou os extremos, comparado com um dia qualquer.
- **Composição automática** (Wikipedia, com cache e lista reserva) para S&P 500, DAX, FTSE 100 e Nifty 50.
- **Novos mercados:** Euro Stoxx 50, FTSE 100, Japão e Índia.
- **China sem ETFs americanos misturados:** a cesta agora tem 42 ações A.
- **Breadth de países:** % dos 43 ETFs de país acima da MA17. Todos usam o mesmo calendário e a mesma moeda (USD).
- **Cripto:** breadth das 23 maiores moedas (sem stablecoins), calculado só em dias úteis para a MA17 ter o mesmo sentido das ações, mais a razão ETH/BTC.
- **Breadth global** ponderado pelo peso aproximado de cada região no MSCI ACWI (edite `weight` em `MARKETS`).

### Como ligar o e-mail diário (uma vez só, cerca de 10 minutos; os arquivos já estão no repositório)

1. **Crie uma senha de app para o e-mail** (a senha normal não funciona por SMTP):
   - **iCloud:** em appleid.apple.com, vá em *Iniciar sessão e segurança* e depois em *Senhas de apps*. Use `SMTP_HOST = smtp.mail.me.com`.
   - **Gmail:** em myaccount.google.com/apppasswords (precisa da verificação em duas etapas). Use `SMTP_HOST = smtp.gmail.com`.
2. **Cadastre os segredos** no repositório, em *Settings → Secrets and variables → Actions → New repository secret*:
   - `SMTP_HOST`: um dos endereços acima
   - `SMTP_PORT`: `587`
   - `SMTP_USER`: o seu endereço de e-mail completo
   - `SMTP_PASS`: a senha de app
   - `EMAIL_TO`: quem recebe (separe vários com vírgula)
3. **(Opcional) Dashboard online:** em *Settings → Pages*, escolha *Deploy from a branch → main → /docs*. Depois, na aba *Variables*, crie `DASHBOARD_URL` com o endereço que o GitHub mostrar. Sem isso, o dashboard vai anexado no e-mail.
4. **Teste agora:** abra a aba *Actions*, escolha *Market Breadth diário* e clique em *Run workflow*.

### Horário
O GitHub só aceita agendamento em UTC. Por isso o workflow tem dois horários e um teste de fuso, que deixa rodar só a execução das 7h30 de Berlim, no inverno e no verão. A execução leva alguns minutos, então o e-mail chega perto das 8h. Em horários de pico, o GitHub às vezes atrasa execuções agendadas em 10 a 30 minutos.

A cada execução o robô grava `docs/` de volta no repositório. Isso tem dois efeitos: o histórico vai crescendo, e o repositório continua ativo (o GitHub desativa agendamentos de repositórios parados há 60 dias).

### Rodar no seu computador ou no notebook

```bash
pip install -r requirements.txt
python market_breadth.py --no-email      # só gera docs/
```

Dentro do Jupyter:

```python
import market_breadth as mb
mb.MA_DAYS = 20          # ajuste fino
mb.main(["--no-email"])
```

### Manutenção

- Uma vez por trimestre, confira a lista "Tickers sem dados" de cada mercado no dashboard e atualize as listas fixas (`IBOV`, `HSI`, `CHINA_A`, `NIKKEI`, `EUROSTOXX50`).
- Os limites ficam no topo do script: `MA_DAYS`, `RSI_OB`/`RSI_OS`, `PCT_LOW`/`PCT_HIGH` e `HISTORY`.

*Ferramenta de estudo, não é recomendação de investimento.*
