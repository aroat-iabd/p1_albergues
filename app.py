"""Aplicación de reservas de Camiño Aberto."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
import os
import time
import uuid
import warnings

from dotenv import load_dotenv
import psycopg2
from psycopg2 import errors
from redis import Redis


# Executa esta comprobación e o decremento como unha única operación
_DECREMENTAR_SE_DISPONIBLE = """
local disponibles = tonumber(redis.call('GET', KEYS[1]))
if not disponibles then
    return -1
end
if disponibles <= 0 then
    return 0
end
redis.call('DECR', KEYS[1])
return 1
"""
# Tempo máximo que unha resposta de dispoñibilidade permanece na caché
_TTL_CACHE_SEGUNDOS = 30


def conectar_postgres():
    """Abre PostgreSQL usando as variables do ficheiro .env."""
    # Carga a configuración e informa con claridade se faltan credenciais obrigatorias
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
    # Decodifica as respostas como texto e verifica a conexión antes de devolvela
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
    # Cada contador identifica un albergue concreto e a noite da reserva
    return f"albergue:dispo:{albergue_id}:{noite.isoformat()}"


def chave_cache(camino, noite):
    # A resposta en caché depende tanto do camiño coma da noite consultada
    return f"cache:dispo:{noite.isoformat()}:{camino}"


def invalidar_cache_noite(cliente_redis, noite):
    # Tras unha reserva, elimina todas as consultas en caché afectadas por esa noite
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
            # Calcula as prazas libres de cada albergue para cada noite con reservas
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

        # A inicialización reconstrúe os contadores e limpa a caché derivada
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
            # Recalcula a dispoñibilidade real para todos os albergues nesa noite
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

    # NX conserva o contador se outro proceso o inicializou mentres se facía a consulta
    pipe = cliente_redis.pipeline(transaction=True)
    for albergue_id, libres in filas:
        pipe.set(chave_dispo(albergue_id, noite), libres, nx=True)
    pipe.execute()


def reservar(albergue_id, noite, peregrino_id):
    """Reserva unha praza con decremento atómico e reverte se falla PostgreSQL."""
    noite = normalizar_noite(noite)
    cliente_redis = conectar_redis()
    clave = chave_dispo(albergue_id, noite)
    try:
        # Se aínda non existe contador para esta noite, créase a partir da bd
        if not cliente_redis.exists(clave):
            inicializar_noite(cliente_redis, noite)

        # A operación decrementar impide que dúas peticións consuman a mesma última praza
        resultado = cliente_redis.eval(_DECREMENTAR_SE_DISPONIBLE, 1, clave)
        if resultado == -1:
            raise RuntimeError(
                f"Non se puido crear o contador de dispoñibilidade {clave}."
            )
        if resultado == 0:
            return False

        try:
            conexion = conectar_postgres()
            try:
                with conexion:
                    with conexion.cursor() as cursor:
                        # PostgreSQL asigna o ID coa secuencia IDENTITY, sen bloquear a táboa.
                        cursor.execute("""
                            INSERT INTO reservas (albergue_id, peregrino_id, data)
                            VALUES (%s, %s, %s)
                        """, (albergue_id, peregrino_id, noite))
            finally:
                conexion.close()
        except Exception as erro:
            # Se PostgreSQL rexeita a reserva, compénsase o decremento feito en Redis
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
            # A reserva xa está gardada; invalídase a caché para non servir datos vellos
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


def consulta_postgres(camino, noite):
    """Devolve os albergues dun camiño con prazas libres nunha noite."""
    noite = normalizar_noite(noite)
    conexion = conectar_postgres()
    try:
        with conexion.cursor() as cursor:
            # Conta as reservas da noite e devolve só os albergues con prazas disponibles
            cursor.execute("""
                SELECT albergues.id, albergues.nome,
                       albergues.prazas - COUNT(reservas.id) AS libres
                FROM albergues
                LEFT JOIN reservas
                    ON reservas.albergue_id = albergues.id
                    AND reservas.data = %s
                WHERE albergues.camino = %s
                GROUP BY albergues.id, albergues.nome, albergues.prazas
                HAVING albergues.prazas - COUNT(reservas.id) > 0
                ORDER BY albergues.id
            """, (noite, camino))
            return [
                {"albergue_id": id_, "nome": nome, "prazas_libres": libres}
                for id_, nome, libres in cursor.fetchall()
            ]
    finally:
        conexion.close()


def consulta_redis(camino, noite):
    """Consulta a dispoñibilidade usando Redis como caché con TTL."""
    noite = normalizar_noite(noite)
    cliente_redis = conectar_redis()
    clave = chave_cache(camino, noite)
    try:
        # Se existe unha resposta recente, devólvese sen repetir a consulta ás bases
        en_cache = cliente_redis.get(clave)
        if en_cache is not None:
            return json.loads(en_cache)

        # En caso de fallo de caché, asegura contadores e obtén nomes/camiño en PostgreSQL
        inicializar_noite(cliente_redis, noite)
        conexion = conectar_postgres()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT id, nome FROM albergues WHERE camino = %s ORDER BY id",
                    (camino,),
                )
                albergues = cursor.fetchall()
        finally:
            conexion.close()

        # Recupera todos os contadores nunha operación Redis e filtra os esgotados
        disponibles = cliente_redis.mget([
            chave_dispo(id_, noite) for id_, _ in albergues
        ])
        resultado = [
            {"albergue_id": id_, "nome": nome, "prazas_libres": int(libres)}
            for (id_, nome), libres in zip(albergues, disponibles)
            if libres is not None and int(libres) > 0
        ]
        # Garda a resposta serializada; o TTL limita canto tempo pode quedar desactualizada
        cliente_redis.setex(
            clave, _TTL_CACHE_SEGUNDOS,
            json.dumps(resultado, ensure_ascii=False),
        )
        return resultado
    finally:
        cliente_redis.close()


def medir_consultas(camino, noite, repetitions=100):
    """Compara o tempo medio dunha consulta en PostgreSQL e da caché Redis."""
    if repetitions <= 0:
        raise ValueError("O número de repeticións debe ser maior que cero.")

    # Quenta a caché antes de medir para comparar consultas repetidas
    consulta_redis(camino, noite)
    inicio = time.perf_counter()
    for _ in range(repetitions):
        consulta_postgres(camino, noite)
    tempo_postgres = (time.perf_counter() - inicio) / repetitions

    inicio = time.perf_counter()
    for _ in range(repetitions):
        consulta_redis(camino, noite)
    tempo_redis = (time.perf_counter() - inicio) / repetitions
    return tempo_postgres * 1000, tempo_redis * 1000


def crear_datos_proba(capacidade, numero_peregrinos):
    # O token evita colisións nos campos únicos ao crear datos temporais para a proba
    token = uuid.uuid4().hex
    conexion = conectar_postgres()
    try:
        with conexion:
            with conexion.cursor() as cursor:
                # Bloquea as táboas mentres se escollen IDs a partir do máximo actual
                cursor.execute("LOCK TABLE albergues IN EXCLUSIVE MODE")
                cursor.execute("LOCK TABLE peregrinos IN EXCLUSIVE MODE")
                cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM albergues")
                albergue_id = cursor.fetchone()[0]
                cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM peregrinos")
                primeiro_id = cursor.fetchone()[0]
                cursor.execute("""
                    INSERT INTO albergues (id, nome, camino, concello, prazas, prezo)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (albergue_id, f"Proba {token}", "__proba__", "Lugo", capacidade, 0))
                peregrinos = list(range(primeiro_id, primeiro_id + numero_peregrinos))
                cursor.executemany("""
                    INSERT INTO peregrinos
                        (id, nome, apelidos, pais, documento, email, data_nacemento, camino)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, [
                    (
                        id_, "Peregrino", token, "Galicia",
                        f"{token}-{indice}", f"{token}-{indice}@example.invalid",
                        date(1990, 1, 1), "__proba__",
                    )
                    for indice, id_ in enumerate(peregrinos)
                ])
        return albergue_id, peregrinos
    finally:
        conexion.close()


def eliminar_datos_proba(albergue_id, peregrinos, noite):
    # Elimina primeiro reservas e peregrinos e despois o albergue de proba
    conexion = conectar_postgres()
    try:
        with conexion:
            with conexion.cursor() as cursor:
                cursor.execute("DELETE FROM reservas WHERE albergue_id = %s", (albergue_id,))
                cursor.execute("DELETE FROM peregrinos WHERE id = ANY(%s)", (peregrinos,))
                cursor.execute("DELETE FROM albergues WHERE id = %s", (albergue_id,))
    finally:
        conexion.close()

    # Limpa tamén o contador e calquera resultado de caché da noite usada
    cliente_redis = conectar_redis()
    try:
        cliente_redis.delete(chave_dispo(albergue_id, noite))
        invalidar_cache_noite(cliente_redis, noite)
    finally:
        cliente_redis.close()


def probar_sobreventa(capacidade=3, intentos=30):
    """Proba reservas concorrentes nun albergue temporal e elimina os datos de proba."""
    if capacidade <= 0 or intentos <= capacidade:
        raise ValueError("Os intentos deben superar unha capacidade maior que cero.")

    # Usa unha noite futura e datos propios para non alterar reservas reais
    noite = date.today() + timedelta(days=30)
    albergue_id, peregrinos = crear_datos_proba(capacidade, intentos)
    try:
        cliente_redis = conectar_redis()
        try:
            cliente_redis.set(chave_dispo(albergue_id, noite), capacidade)
        finally:
            cliente_redis.close()

        # Cada peregrino envía unha petición en paralelo para disputar as mesmas prazas
        with ThreadPoolExecutor(max_workers=intentos) as executor:
            resultados = list(executor.map(
                lambda peregrino_id: reservar(albergue_id, noite, peregrino_id),
                peregrinos,
            ))
        confirmadas = sum(resultados)
        if confirmadas != capacidade:
            raise AssertionError(
                f"Esperábanse {capacidade} reservas; confirmáronse {confirmadas}."
            )
        print(
            f"Proba superada: {confirmadas} reservas confirmadas de {intentos}; "
            "sen sobreventa."
        )
        return confirmadas
    finally:
        eliminar_datos_proba(albergue_id, peregrinos, noite)


def main():
    # Define subcomandos para preparar Redis, probar a sobreventa e medir consultas
    parser = argparse.ArgumentParser(description="Aplicación de reservas Camiño Aberto")
    subparsers = parser.add_subparsers(dest="comando", required=True)
    subparsers.add_parser(
        "inicializar",
        help="construír os contadores de Redis a partir das reservas de PostgreSQL",
    )

    proba = subparsers.add_parser(
        "probar-sobreventa",
        help="lanzar reservas simultáneas para comprobar que non hai sobreventa",
    )
    proba.add_argument("--prazas", type=int, default=3)
    proba.add_argument("--intentos", type=int, default=30)

    medir = subparsers.add_parser(
        "medir",
        help="comparar o tempo de consulta en PostgreSQL e Redis",
    )
    medir.add_argument("--camino", default="Francés")
    medir.add_argument("--noite", type=date.fromisoformat, default=date.today())
    medir.add_argument("--repeticions", type=int, default=100)

    # Executa a operación solicitada cos parámetros da liña de comandos
    args = parser.parse_args()
    if args.comando == "inicializar":
        inicializar_contadores()
    elif args.comando == "probar-sobreventa":
        probar_sobreventa(args.prazas, args.intentos)
    elif args.comando == "medir":
        postgres_ms, redis_ms = medir_consultas(
            args.camino, args.noite, args.repeticions
        )
        print(
            f"Tempo medio en {args.repeticions} consultas: "
            f"PostgreSQL {postgres_ms:.3f} ms; Redis/caché {redis_ms:.3f} ms."
        )


if __name__ == "__main__":
    main()