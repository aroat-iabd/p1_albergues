
#!/usr/bin/env bash

# Detén o script se hai erros ou variables sen definir
set -euo pipefail

# Permisos privados para os ficheiros de copia
umask 077

# Localiza a raíz do proxecto, independentemente de onde se execute
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"


# Modo de funcionamento: backup por defecto
MODO="${1:-backup}"


# Restaurar sobre unha base de proba xa existente
if [[ "$MODO" == "restaurar-en" ]]; then

    if [[ $# -ne 4 ]]; then
        echo "Uso: bash src/copia.sh restaurar-en BD_PROBA FICHEIRO_PG FICHEIRO_MONGO" >&2
        exit 1
    fi

    BD_DESTINO="$2"
    FICHEIRO_PG="$3"
    FICHEIRO_MONGO="$4"

    # Medida de seguridade: só permitimos bases de proba
    if [[ ! "$BD_DESTINO" =~ ^albergues_proba_[0-9]{8}_[0-9]{6}$ ]]; then
        echo "Erro: só se permite restaurar en bases de proba con data e hora." >&2
        exit 1
    fi

    # Comprobar a existencia e o formato das copias
    if [[ ! -s "$FICHEIRO_PG" || ! -s "$FICHEIRO_MONGO" ]]; then
        echo "Erro: faltan os ficheiros de copia." >&2
        exit 1
    fi

    docker compose exec -T postgres pg_restore --list \
        < "$FICHEIRO_PG" > /dev/null

    gzip -t "$FICHEIRO_MONGO"

    # Comprobar que a base PostgreSQL de destino existe
    docker compose exec -T postgres sh -c '
        psql -U "$POSTGRES_USER" -d "$1" -Atqc "SELECT 1"
    ' sh "$BD_DESTINO" > /dev/null

    echo "Restaurando PostgreSQL en $BD_DESTINO..."

    docker compose exec -T postgres sh -c '
        pg_restore \
            -U "$POSTGRES_USER" \
            -d "$1" \
            --clean \
            --if-exists \
            --no-owner \
            --no-acl \
            --single-transaction
    ' sh "$BD_DESTINO" < "$FICHEIRO_PG"

    echo "PostgreSQL restaurado correctamente."

    echo "Restaurando MongoDB en $BD_DESTINO..."

    docker compose exec -T mongo sh -c '
        exec mongorestore \
            --host 127.0.0.1 \
            --username "$MONGO_INITDB_ROOT_USERNAME" \
            --password "$MONGO_INITDB_ROOT_PASSWORD" \
            --authenticationDatabase admin \
            --archive \
            --gzip \
            --drop \
            --nsFrom="$MONGO_INITDB_DATABASE.*" \
            --nsTo="$1.*"
    ' sh "$BD_DESTINO" < "$FICHEIRO_MONGO"

    echo "MongoDB restaurado correctamente."
    echo "Recuperación finalizada en $BD_DESTINO."

    exit 0
fi

if [[ "$MODO" == "restaurar" ]]; then

    # Necesitamos os dous ficheiros de copia
    if [[ $# -ne 3 ]]; then
        echo "Uso: bash src/copia.sh restaurar FICHEIRO_PG FICHEIRO_MONGO"
        exit 1
    fi

    FICHEIRO_PG="$2"
    FICHEIRO_MONGO="$3"

    # Comprobamos que existen e non están baleiros
    if [[ ! -s "$FICHEIRO_PG" || ! -s "$FICHEIRO_MONGO" ]]; then
        echo "Erro: non se atoparon os ficheiros de copia." >&2
        exit 1
    fi

    # Verificamos os formatos antes de restaurar
    docker compose exec -T postgres pg_restore --list \
        < "$FICHEIRO_PG" > /dev/null

    gzip -t "$FICHEIRO_MONGO"

    # Creamos unha base de proba distinta en cada execución
    DATA_PROBA=$(date +"%Y%m%d_%H%M%S")
    BD_PROBA="albergues_proba_${DATA_PROBA}"

    echo "Restaurando PostgreSQL en: $BD_PROBA"

    # Crear base de datos PostgreSQL baleira
    docker compose exec -T postgres sh -c \
        'createdb -U "$POSTGRES_USER" "$1"' sh "$BD_PROBA"

    # Restaurar as táboas, datos e restricións
    docker compose exec -T postgres sh -c '
        pg_restore \
            -U "$POSTGRES_USER" \
            -d "$1" \
            --no-owner \
            --no-acl \
            --exit-on-error
    ' sh "$BD_PROBA" < "$FICHEIRO_PG"

    echo "PostgreSQL restaurado correctamente."

    echo "Restaurando MongoDB en: $BD_PROBA"

    # Restaurar MongoDB nunha base de datos de proba
    docker compose exec -T mongo sh -c '
        exec mongorestore \
            --host 127.0.0.1 \
            --username "$MONGO_INITDB_ROOT_USERNAME" \
            --password "$MONGO_INITDB_ROOT_PASSWORD" \
            --authenticationDatabase admin \
            --archive \
            --gzip \
            --nsFrom="$MONGO_INITDB_DATABASE.*" \
            --nsTo="$1.*"
    ' sh "$BD_PROBA" < "$FICHEIRO_MONGO"

    echo "MongoDB restaurado correctamente."
    echo "Restauración finalizada na base: $BD_PROBA"

    exit 0

elif [[ "$MODO" != "backup" ]]; then

    echo "Modo non válido: $MODO" >&2
    echo "Modos dispoñibles: backup, restaurar"
    exit 1

fi

# Crea o cartafol de copias se non existe
mkdir -p copias

# Data e hora para identificar cada copia
DATA=$(date +"%Y-%m-%d_%H-%M-%S")

# Ruta do ficheiro de PostgreSQL
FICHEIRO_PG="copias/postgres_${DATA}.dump"

echo "Iniciando copia de seguridade de PostgreSQL..."

# Executa pg_dump dentro do contedor e garda o resultado no equipo
if ! docker compose exec -T postgres \
    sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
    > "$FICHEIRO_PG"; then

    rm -f "$FICHEIRO_PG"
    echo "Erro ao crear a copia de PostgreSQL." >&2
    exit 1
fi

# Comproba que o ficheiro non está baleiro
if [[ ! -s "$FICHEIRO_PG" ]]; then
    rm -f "$FICHEIRO_PG"
    echo "Erro: a copia está baleira." >&2
    exit 1
fi

echo "Copia de PostgreSQL creada: $FICHEIRO_PG"


# ------------------------------------------------------------------ MongoDB

# Ruta do ficheiro comprimido de MongoDB
FICHEIRO_MONGO="copias/mongo_${DATA}.archive.gz"

echo "Iniciando copia de seguridade de MongoDB..."

# Executa mongodump dentro do contedor
if ! docker compose exec -T mongo sh -c '
    exec mongodump \
        --host 127.0.0.1 \
        --username "$MONGO_INITDB_ROOT_USERNAME" \
        --password "$MONGO_INITDB_ROOT_PASSWORD" \
        --authenticationDatabase admin \
        --db "$MONGO_INITDB_DATABASE" \
        --archive \
        --gzip
' > "$FICHEIRO_MONGO"; then

    rm -f "$FICHEIRO_MONGO"
    echo "Erro ao crear a copia de MongoDB." >&2
    exit 1
fi

# Comproba que a copia non está baleira
if [[ ! -s "$FICHEIRO_MONGO" ]]; then
    rm -f "$FICHEIRO_MONGO"
    echo "Erro: a copia de MongoDB está baleira." >&2
    exit 1
fi

echo "Copia de MongoDB creada: $FICHEIRO_MONGO"
echo "Copias de seguridade finalizadas."