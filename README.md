# Mateus Imports — loja + painel (FastAPI + SQLite)

Uma única aplicação serve tudo, com banco **SQLite** (um arquivo `mateus.db`, sem instalar servidor de banco e sem Docker):
- **Loja:** http://localhost:8000/
- **Painel do dono:** http://localhost:8000/admin
- **API (documentação automática):** http://localhost:8000/docs

## Instalação (Windows, Linux ou Mac) — só precisa do Python 3.11+

1. **Configuração.** Copie `.env.example` para `.env` e edite `JWT_SECRET` (texto longo e aleatório),
   `ADMIN_EMAIL` e `ADMIN_PASSWORD` (login do painel, criado na primeira execução).
2. **Dependências** (dentro da pasta do projeto):
   ```
   python -m venv .venv
   .venv\Scripts\activate        (Windows)   |   source .venv/bin/activate   (Linux/Mac)
   pip install -r requirements.txt
   ```
3. **Iniciar:** `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
   (use sempre **um único processo**; não adicione `--workers`).
   Na primeira vez, o servidor cria o banco e **importa sozinho** as 11 categorias e 93 produtos do site antigo
   (para desativar, coloque `AUTO_SEED=0` no `.env`). Abra a loja sempre pelo endereço do servidor, nunca clicando no arquivo `index.html`.

O arquivo `mateus.db` é criado dentro da pasta do projeto, de qualquer lugar que você inicie o servidor.

## Depois de instalar
No painel (/admin) → **Configurações**, confira WhatsApp, endereço, PIX e o valor da 99Moto.
Em **Produtos**, ajuste o estoque (importado com 10 em todos) e as variações (moletons, Coffey Beach Wear).
Três T-shirts Polo ficaram de fora por falta de preço visível.

## Backup
Copie o arquivo `mateus.db` (com a aplicação parada, ou use `sqlite3 mateus.db ".backup copia.db"`). Faça isso com frequência.

## Produção
- Coloque atrás de HTTPS (Caddy/Nginx) e mantenha `.env` e `mateus.db` fora do alcance público.
- Ainda não incluído: limite de tentativas de login, fotos em arquivos (hoje ficam dentro do banco) e frete automático dos Correios.

## Testes
`pytest -q tests` (usa um SQLite temporário; não mexe no seu `mateus.db`).

## Estrutura
- `app/models.py` tabelas · `app/main.py` API, regras de pedido e rotas do site
- `static/index.html` loja · `static/admin.html` painel
- `schema.sql` tabelas em SQL (referência) · `data/catalogo.json` catálogo importado

## Catálogo protegido (nada some sozinho)
- **Backups automáticos:** ao iniciar, a cada 6 horas e antes de qualquer exclusão, o servidor copia o banco para a pasta `backups/` (mantém as últimas 14). Para restaurar: pare o servidor, copie um arquivo de `backups/` por cima de `mateus.db` e inicie de novo.
- **Importação automática:** se o banco ficar sem nenhum produto, o catálogo inicial é importado de novo ao reiniciar.
- **Cópia na loja:** o navegador do cliente guarda a última versão do catálogo; se o servidor falhar por um instante, os produtos continuam aparecendo (com um aviso).
- **O que esconde produtos de propósito:** status *Inativo* no produto ou na categoria. Produto sem estoque continua aparecendo, marcado como "Sem estoque".
