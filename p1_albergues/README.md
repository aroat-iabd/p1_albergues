# P1 · Reservas de albergues do Camiño — plantilla

Punto de partida do proxecto. Le antes o enunciado (`BDA_UD1_P1_Reservas_albergues`).

## Que trae

| Ficheiro | Estado |
|---|---|
| `.env.example` | Variables de conexión. Cópiao como `.env` e cambia os contrasinais. |
| `.gitignore` | Deixa fóra do repositorio `.env`, `copias/` e o contorno virtual. |
| `requirements.txt` | Librarías de Python con versión fixada. |
| `src/xera_datos.py` | Esqueleto do xerador. `xera_albergues()` está feita como exemplo; o resto ten `TODO`. |
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

# 4. Executade o xerador: xa funciona, aínda que só xera albergues
python -m src.xera_datos --sen-carga
```

Seguinte paso: completar `xera_peregrinos()`.

## Comprobar a reproducibilidade

Executade o xerador dúas veces coa mesma semente e comparade:

```bash
python -m src.xera_datos --sen-carga --semente 7 > a.txt
python -m src.xera_datos --sen-carga --semente 7 > b.txt
diff a.txt b.txt && echo "Reproducible"
```

## Orde recomendada

1. `xera_peregrinos()`, `xera_reservas()` e `xera_fichas()` con `--sen-carga`.
2. `compose.yaml` con PostgreSQL e Redis (podedes partir do do obradoiro).
3. Esquema de PostgreSQL e `carga_postgres()`.
4. Redis: contadores, `reservar()`, proba de sobreventa e caché.
5. MongoDB (verase máis adiante): servizo no compose e `carga_mongo()`.
6. `src/copia.sh` e proba de restauración.
7. Medicións e README.

Facede un *commit* ao rematar cada paso: se algo se rompe, podedes volver atrás.
