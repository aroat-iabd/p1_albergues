# P1 · Reservas de albergues do Camiño — plantilla

Punto de partida do proxecto. Le antes o enunciado (`BDA_UD1_P1_Reservas_albergues`).

## Que trae

| Ficheiro | Estado |
|---|---|
| `.env.example` | Variables de conexión. Cópiao como `.env` e cambia os contrasinais. |
| `.gitignore` | Deixa fóra do repositorio `.env`, `copias/` e o contorno virtual. |
| `requirements.txt` | Librarías de Python con versión fixada. |
| `src/xera_datos.py` | Xeración de albergues, peregrinos, reservas e fichas; carga PostgreSQL implementada. A carga MongoDB segue pendente. |
| `src/__init__.py` | Fai de `src` un paquete de Python (permite `from src.modulo import ...`). |

Todo o demais (`compose.yaml`, esquema da base de datos, código de Redis, copias, README final) facédelo vós.

## Estrutura do repositorio

Mantede sempre esta estrutura:

```text
p1-albergues/
├── app.py            (opcional) aplicación principal; tamén pode chamarse main.py
├── compose.yaml
├── .env.example
├── requirements.txt
├── README.md
└── src/              todo o resto do código: módulos de Python e scripts (.py, .sh)
    ├── __init__.py
    └── xera_datos.py
```

- Na raíz só van a configuración, o README e, se o hai, o punto de entrada (`app.py` ou `main.py`).
- Os scripts execútanse **desde a raíz**: `python -m src.xera_datos`, `python app.py …`, `./src/copia.sh`.
- Entre módulos de `src`, importade co prefixo do paquete: `from src.conexions import postgres`.

## Primeiros pasos

O proxecto é **por parellas** e entrégase **só** no repositorio de GitHub.

```bash
# 1. UN membro: crea un repositorio baleiro en GitHub (sen README) e sube a plantilla (acceso por SSH)
git init -b main
git add . && git commit -m "Plantilla P1"
git remote add origin git@github.com:USUARIO/p1-albergues.git
git push -u origin main
#    En GitHub › Settings › Collaborators: convida á túa parella
#    (e ao docente, se o repositorio é privado)

# 2. O OUTRO membro: clona o repositorio
git clone git@github.com:USUARIO/p1-albergues.git

# 3. Os dous: contorno virtual e dependencias
python -m venv .venv
source .venv/bin/activate          # en Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4. Executade o xerador sen cargar os datos nas bases
python -m src.xera_datos --sen-carga
```

## Carga en PostgreSQL

Desde a raíz do proxecto, copia `.env.example` como `.env` e configura as
credenciais. Inicia o servizo definido en `compose.yaml` e executa o xerador sen
`--sen-carga`:

```bash
docker compose up -d postgres
python -m src.xera_datos
```

`carga_postgres()` crea as táboas necesarias e substitúe os datos relacionales
previos pola xeración actual nunha única transacción. Isto elimina as reservas
novas creadas pola aplicación; úsao só cando queiras reiniciar o estado inicial.
`carga_mongo()` actualiza as fichas xeradas e elimina as que xa non correspondan
a un albergue da xeración actual.

## Comprobar a reproducibilidade

Executade o xerador dúas veces coa mesma semente e comparade:

```bash
python -m src.xera_datos --sen-carga --semente 7 > a.txt
python -m src.xera_datos --sen-carga --semente 7 > b.txt
diff a.txt b.txt && echo "Reproducible"
```

## Orde recomendada

1. Probar `xera_peregrinos()`, `xera_reservas()` e `xera_fichas()` con `--sen-carga`.
2. PostgreSQL: iniciar o servizo con `docker compose up -d postgres` e probar `carga_postgres()`.
4. Redis: contadores, `reservar()`, proba de sobreventa e caché.
5. MongoDB (verase máis adiante): servizo no compose e `carga_mongo()`.
6. `src/copia.sh` e proba de restauración.
7. Medicións e README.

Facede un *commit* ao rematar cada paso: se algo se rompe, podedes volver atrás.
