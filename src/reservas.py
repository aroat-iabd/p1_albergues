"""Conexións, contadores Redis e creación atómica de reservas."""
import os
import warnings
from datetime import date

from dotenv import load_dotenv
import psycopg2
from psycopg2 import errors
from redis import Redis


# Redis executa a comprobación e o decremento como unha única operación atómica.
_DECREMENTAR_SE_DISPONIBLE = """
local valor = redis.call('GET', KEYS[1])
if not valor then
    return -1
end
if not string.match(valor, '^%d+$') then
    return -1
end
local disponibles = tonumber(valor)
if not disponibles or disponibles < 0 or disponibles % 1 ~= 0 then
    return -1
end
if disponibles == 0 then
    return 0
end
redis.call('DECR', KEYS[1])
return 1
"""


def conectar_postgres():
    """Abre PostgreSQL usando as variables do ficheiro .env."""
    load_dotenv()
    requiridas = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    ausentes = [nome for nome in requiridas if not os.getenv(nome)]
    if ausentes:
        raise RuntimeError(
            "Faltan variables de PostgreSQL no .env: " + ", ".join(ausentes)
        )

    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def conectar_redis():
    """Abre Redis e comproba que o servizo responde."""
    load_dotenv()
    cliente = Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )
    cliente.ping()
    return cliente


def normalizar_noite(noite):
    """Converte unha data ou cadea ISO nun obxecto date."""
    if isinstance(noite, date):
        return noite
    return date.fromisoformat(noite)


def chave_dispo(albergue_id, noite):
    """Constrúe a clave do contador dun albergue e unha noite."""
    return f"albergue:dispo:{albergue_id}:{noite.isoformat()}"


def chave_cache(camino, noite):
    """Constrúe a clave da caché dunha consulta por camiño e noite."""
    return f"cache:dispo:{noite.isoformat()}:{camino}"


def invalidar_cache_noite(cliente_redis, noite):
    """Elimina as consultas en caché afectadas por unha reserva nesa noite."""
    claves = list(
        cliente_redis.scan_iter(match=f"cache:dispo:{noite.isoformat()}:*")
    )
    if claves:
        cliente_redis.delete(*claves)


def inicializar_contadores():
    """Crea un contador por albergue e noite con reservas xa existentes."""
    cliente_redis = conectar_redis()
    conexion = conectar_postgres()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT noites.data, albergues.id,
                       GREATEST(albergues.prazas - COUNT(reservas.id), 0)
                FROM (SELECT DISTINCT data FROM reservas) AS noites
                CROSS JOIN albergues
                LEFT JOIN reservas
                    ON reservas.data = noites.data
                    AND reservas.albergue_id = albergues.id
                GROUP BY noites.data, albergues.id, albergues.prazas
                ORDER BY noites.data, albergues.id
            """)
            filas = cursor.fetchall()

        # A inicialización reconstrúe os contadores e limpa a caché derivada.
        claves = list(cliente_redis.scan_iter(match="albergue:dispo:*"))
        claves += list(cliente_redis.scan_iter(match="cache:dispo:*"))
        pipe = cliente_redis.pipeline(transaction=True)
        if claves:
            pipe.delete(*claves)
        for noite, albergue_id, libres in filas:
            pipe.set(chave_dispo(albergue_id, noite), libres)
        pipe.execute()
        print(f"Redis inicializado con {len(filas)} contadores.")
        return len(filas)
    finally:
        conexion.close()
        cliente_redis.close()


def inicializar_noite(cliente_redis, noite):
    """Crea, se falta, os contadores dunha noite a partir de PostgreSQL."""
    conexion = conectar_postgres()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT albergues.id,
                       GREATEST(albergues.prazas - COUNT(reservas.id), 0)
                FROM albergues
                LEFT JOIN reservas
                    ON reservas.albergue_id = albergues.id
                    AND reservas.data = %s
                GROUP BY albergues.id, albergues.prazas
            """, (noite,))
            filas = cursor.fetchall()
    finally:
        conexion.close()

    # NX evita que un cálculo simultáneo sobrescriba un contador xa inicializado.
    pipe = cliente_redis.pipeline(transaction=True)
    for albergue_id, libres in filas:
        pipe.set(chave_dispo(albergue_id, noite), libres, nx=True)
    pipe.execute()


def reservar(albergue_id, noite, peregrino_id):
    """Reserva unha praza atomicamente e compensa Redis se falla PostgreSQL."""
    noite = normalizar_noite(noite)
    cliente_redis = conectar_redis()
    clave = chave_dispo(albergue_id, noite)
    try:
        if not cliente_redis.exists(clave):
            inicializar_noite(cliente_redis, noite)

        resultado = cliente_redis.eval(_DECREMENTAR_SE_DISPONIBLE, 1, clave)
        if resultado == -1:
            raise RuntimeError(
                f"Non se puido crear ou validar o contador de dispoñibilidade {clave}."
            )
        if resultado == 0:
            return False

        try:
            conexion = conectar_postgres()
            try:
                with conexion:
                    with conexion.cursor() as cursor:
                        # PostgreSQL xera o ID da reserva coa súa secuencia IDENTITY.
                        cursor.execute("""
                            INSERT INTO reservas (albergue_id, peregrino_id, data)
                            VALUES (%s, %s, %s)
                        """, (albergue_id, peregrino_id, noite))
            finally:
                conexion.close()
        except Exception as erro:
            try:
                cliente_redis.incr(clave)
            except Exception as erro_redis:
                raise RuntimeError(
                    f"Fallou PostgreSQL e non se puido restaurar o contador {clave}; "
                    "cómpre reconciliar a dispoñibilidade."
                ) from erro_redis
            if isinstance(erro, errors.UniqueViolation):
                return False
            raise

        try:
            invalidar_cache_noite(cliente_redis, noite)
        except Exception as erro_cache:
            warnings.warn(
                "A reserva completouse, pero non se puido invalidar a caché; "
                f"o resultado pode quedar desactualizado ata que expire o TTL. {erro_cache}",
                RuntimeWarning,
                stacklevel=2,
            )
        return True
    finally:
        cliente_redis.close()
