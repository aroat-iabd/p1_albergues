"""Consultas de dispoñibilidade, medicións e proba concorrente de reservas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
import time
import uuid

from src.reservas import (
    chave_cache,
    chave_dispo,
    conectar_postgres,
    conectar_redis,
    invalidar_cache_noite,
    inicializar_noite,
    normalizar_noite,
    reservar,
)


# Limita canto tempo pode permanecer na caché unha resposta de dispoñibilidade.
_TTL_CACHE_SEGUNDOS = 30


def consulta_postgres(camino, noite):
    """Devolve os albergues dun camiño con prazas libres nunha noite."""
    noite = normalizar_noite(noite)
    conexion = conectar_postgres()
    try:
        with conexion.cursor() as cursor:
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
        en_cache = cliente_redis.get(clave)
        if en_cache is not None:
            return json.loads(en_cache)

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

        disponibles = cliente_redis.mget([
            chave_dispo(id_, noite) for id_, _ in albergues
        ])
        resultado = [
            {"albergue_id": id_, "nome": nome, "prazas_libres": int(libres)}
            for (id_, nome), libres in zip(albergues, disponibles)
            if libres is not None and int(libres) > 0
        ]
        cliente_redis.setex(
            clave,
            _TTL_CACHE_SEGUNDOS,
            json.dumps(resultado, ensure_ascii=False),
        )
        return resultado
    finally:
        cliente_redis.close()


def medir_consultas(camino, noite, repetitions=100):
    """Compara o tempo medio dunha consulta en PostgreSQL e da caché Redis."""
    if repetitions <= 0:
        raise ValueError("O número de repeticións debe ser maior que cero.")

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
    """Crea un albergue e peregrinos temporais con IDs xerados por PostgreSQL."""
    token = uuid.uuid4().hex
    conexion = conectar_postgres()
    try:
        with conexion:
            with conexion.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO albergues (nome, camino, concello, prazas, prezo)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (f"Proba {token}", "__proba__", "Lugo", capacidade, 0))
                albergue_id = cursor.fetchone()[0]

                peregrinos = []
                for indice in range(numero_peregrinos):
                    cursor.execute("""
                        INSERT INTO peregrinos
                            (nome, apelidos, pais, documento, email, data_nacemento, camino)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        "Peregrino",
                        token,
                        "Galicia",
                        f"{token}-{indice}",
                        f"{token}-{indice}@example.invalid",
                        date(1990, 1, 1),
                        "__proba__",
                    ))
                    peregrinos.append(cursor.fetchone()[0])
        return albergue_id, peregrinos
    finally:
        conexion.close()


def eliminar_datos_proba(albergue_id, peregrinos, noite):
    """Elimina os rexistros temporais e o contador usado na proba."""
    conexion = conectar_postgres()
    try:
        with conexion:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM reservas WHERE albergue_id = %s", (albergue_id,)
                )
                cursor.execute(
                    "DELETE FROM peregrinos WHERE id = ANY(%s)", (peregrinos,)
                )
                cursor.execute("DELETE FROM albergues WHERE id = %s", (albergue_id,))
    finally:
        conexion.close()

    cliente_redis = conectar_redis()
    try:
        cliente_redis.delete(chave_dispo(albergue_id, noite))
        invalidar_cache_noite(cliente_redis, noite)
    finally:
        cliente_redis.close()


def probar_sobreventa(capacidade=3, intentos=30):
    """Verifica en paralelo os límites e a coherencia entre PostgreSQL e Redis."""
    if capacidade <= 0 or intentos <= capacidade:
        raise ValueError("Os intentos deben superar unha capacidade maior que cero.")

    noite = date.today() + timedelta(days=30)
    albergue_id, peregrinos = crear_datos_proba(capacidade, intentos)
    try:
        cliente_redis = conectar_redis()
        try:
            cliente_redis.set(chave_dispo(albergue_id, noite), capacidade)
        finally:
            cliente_redis.close()

        with ThreadPoolExecutor(max_workers=intentos) as executor:
            resultados = list(executor.map(
                lambda peregrino_id: reservar(albergue_id, noite, peregrino_id),
                peregrinos,
            ))
        confirmadas = sum(resultados)

        conexion = conectar_postgres()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM reservas "
                    "WHERE albergue_id = %s AND data = %s",
                    (albergue_id, noite),
                )
                reservas_postgres = cursor.fetchone()[0]
        finally:
            conexion.close()

        cliente_redis = conectar_redis()
        try:
            restantes_redis = cliente_redis.get(chave_dispo(albergue_id, noite))
        finally:
            cliente_redis.close()

        if confirmadas != capacidade:
            raise AssertionError(
                f"Esperábanse {capacidade} confirmacións; houbo {confirmadas}."
            )
        if reservas_postgres != confirmadas:
            raise AssertionError(
                f"PostgreSQL garda {reservas_postgres} reservas, "
                f"pero a aplicación confirmou {confirmadas}."
            )
        if restantes_redis is None or int(restantes_redis) + reservas_postgres != capacidade:
            raise AssertionError(
                f"Contador Redis incoherente: quedan {restantes_redis!r} prazas "
                f"e PostgreSQL garda {reservas_postgres} reservas para capacidade "
                f"{capacidade}."
            )

        print(
            f"Proba superada: {confirmadas}/{intentos} intentos confirmados; "
            f"PostgreSQL={reservas_postgres}, Redis={restantes_redis} prazas libres, "
            "sen sobreventa e con contadores coherentes."
        )
        return confirmadas
    finally:
        eliminar_datos_proba(albergue_id, peregrinos, noite)
