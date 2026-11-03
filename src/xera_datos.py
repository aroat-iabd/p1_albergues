"""Xerador de datos de proba para a rede de albergues Camiño Aberto (ficticia).

ESQUELETO DO P1. Xa funciona: xera albergues e mostra un resumo. O resto
das funcións están marcadas con TODO e, mentres non as completes, avisan
e devolven unha lista baleira para que o script se poida executar desde o
primeiro día.

Exemplos (desde a raíz do proxecto):
  python -m src.xera_datos --sen-carga                    # só xerar e mostrar
  python -m src.xera_datos --albergues 60 --semente 7 --sen-carga
  python -m src.xera_datos                                 # xerar e cargar (cando estea feito)
"""
import argparse
import random
from datetime import date, timedelta

from faker import Faker

# ------------------------------------------------------------------ catálogos
# Concellos galegos de cada camiño, en orde de etapas. Podes engadir máis.
CAMIÑOS = {
    "Francés":   ["Pedrafita do Cebreiro", "Triacastela", "Samos", "Sarria", "Portomarín",
                  "Palas de Rei", "Melide", "Arzúa", "O Pino"],
    "Portugués": ["Tui", "O Porriño", "Redondela", "Pontevedra", "Caldas de Reis", "Padrón", "Teo"],
    "Norte":     ["Ribadeo", "Lourenzá", "Mondoñedo", "Abadín", "Vilalba", "Guitiriz", "Sobrado"],
    "Primitivo": ["A Fonsagrada", "Castroverde", "Lugo", "Friol", "Melide"],
    "Inglés":    ["Ferrol", "Neda", "Pontedeume", "Betanzos", "Abegondo", "Ordes"],
}
NOMES_ALBERGUE = ["Vieiras", "Pedra Miúda", "O Cruceiro", "A Ponte Vella", "Bordón", "A Cabaciña",
                  "Fonte Vella", "Os Carballos", "A Estrela", "Camiño Real", "Casa do Peregrino",
                  "A Xesta", "O Muíño", "Santa Mariña", "O Hórreo", "A Lareira", "Sete Fontes"]


def pendente(nome):
    print(f"  [pendente] {nome}() aínda non está feita")
    return []


# ------------------------------------------------------------------ xeración
def xera_albergues(n, rng):
    """EXEMPLO RESOLTO: úsao como modelo para o resto de funcións.

    Devolve unha lista de dicionarios, un por albergue. Todo o azar sae de `rng`
    (un random.Random), non do módulo `random` directamente: así a semente controla
    o resultado.
    """
    albergues = []
    for i in range(1, n + 1):
        camino = rng.choice(list(CAMIÑOS))
        concello = rng.choice(CAMIÑOS[camino])
        albergues.append({
            "id": i,
            "nome": f"Albergue {rng.choice(NOMES_ALBERGUE)} ({concello})",
            "camino": camino,
            "concello": concello,
            "prazas": rng.randint(8, 60),
            "prezo": float(rng.randint(10, 22)),
        })
    return albergues


def xera_peregrinos(n, rng, fake):
    
    peregrinos = []
    #lista de fakers por país, para poder xerar nomes e apelidos realistas
    fakers = {
        "es_ES": Faker("es_ES"),
        "pt_PT": Faker("pt_PT"),
        "de_DE": Faker("de_DE"),
    }
    paises = {
        "es_ES": "España",
        "pt_PT": "Portugal",
        "de_DE": "Alemania",
    }

    for i in range(1, n + 1):
        #camiño e país aleatorio para cada peregrino
        camino = rng.choice(list(CAMIÑOS))
        locale = rng.choice(list(fakers))
        fake_pais = fakers[locale]

        peregrinos.append({
            "id": i,
            "nome": fake_pais.first_name(),
            "apelidos": fake_pais.last_name(),
            "pais": paises[locale],
            "documento": fake.unique.ssn(),
            "email": fake.unique.email(),
            "data_nacemento": fake.date_of_birth(minimum_age=18, maximum_age=80).isoformat(),
            "camino": camino
        })
    
    return peregrinos


def xera_reservas(n, albergues, peregrinos, desde, dias, rng):

    reservas = []

    # Sen datos ou cun límite/período baleiro, non hai reservas posibles
    if n <= 0 or dias <= 0 or not albergues or not peregrinos:
        return reservas

    # Garda por noite os peregrinos dispoñibles e as prazas que quedan en cada albergue
    noites = []
    for offset in range(dias):
        albergues_disponibles = [
            (albergue, albergue["prazas"])
            for albergue in albergues
            if albergue["prazas"] > 0
        ]
        # Cada peregrino pode reservar unha vez en cada noite
        peregrinos_disponibles = peregrinos.copy()
        if albergues_disponibles:
            noites.append({
                "data": desde + timedelta(days=offset),
                "albergues": albergues_disponibles,
                "peregrinos": peregrinos_disponibles,
            })

    # Escolle noites ao azar ata chegar a n ou esgotar a dispoñibilidade
    while len(reservas) < n and noites:
        noite_i = rng.randrange(len(noites))
        noite = noites[noite_i]

        # Retira o peregrino escollido para impedir que repita esa mesma noite
        peregrino_i = rng.randrange(len(noite["peregrinos"]))
        peregrino = noite["peregrinos"][peregrino_i]
        noite["peregrinos"][peregrino_i] = noite["peregrinos"][-1]
        noite["peregrinos"].pop()

        # Escolle un albergue e consume unha das súas prazas dispoñibles
        albergue_i = rng.randrange(len(noite["albergues"]))
        albergue, prazas = noite["albergues"][albergue_i]
        if prazas == 1:
            noite["albergues"][albergue_i] = noite["albergues"][-1]
            noite["albergues"].pop()
        else:
            noite["albergues"][albergue_i] = (albergue, prazas - 1)

        # Engade a reserva coas referencias e a data da noite seleccionada
        reservas.append({
            "id": len(reservas) + 1,
            "albergue_id": albergue["id"],
            "peregrino_id": peregrino["id"],
            "data": noite["data"].isoformat(),
        })

        # Descarta a noite cando xa non quedan prazas ou peregrinos nela
        if not noite["albergues"] or not noite["peregrinos"]:
            noites[noite_i] = noites[-1]
            noites.pop()

    return reservas


def xera_fichas(albergues, rng, fake):

    fichas = []
    # Catálogos cos que se compoñen os servizos, idiomas e opinións
    servizos_posibles = [
        "cociña", "lavadora", "wifi", "almorzo", "duchas quentes",
        "secador", "toallas",
    ]
    idiomas_posibles = ["galego", "castelán", "inglés", "francés", "portugués", "alemán"]
    textos_opinion = [
        "Moi limpo", "Boa atención", "Almorzo estupendo",
        "Moi ben situado", "Un lugar acolledor",
    ]

    for albergue in albergues:
        # Decide si é publico ou privado e xera un horario para este albergue
        publico = rng.choice([True, False])
        apertura = rng.randint(11, 15)
        peche = rng.randint(max(apertura + 5, 20), 23)

        # A ficha sempre inclúe identificación, camiño, servizos, horario e titularidade
        ficha = {
            "albergue_id": albergue["id"],
            "nome": (
                f"Albergue público de {albergue['concello']}"
                if publico else albergue["nome"]
            ),
            "camino": albergue["camino"],
            "servizos": rng.sample(servizos_posibles, rng.randint(2, 5)),
            "horario": {
                "apertura": f"{apertura:02d}:00",
                "peche": f"{peche:02d}:{rng.choice(['00', '30'])}",
            },
            "titularidade": "Xunta de Galicia" if publico else "Privada",
        }

        # Os privados poden ter datos de contacto; a web é opcional mesmo nese caso
        if not publico and rng.random() < 0.8:
            contacto = {"telefono": fake.phone_number()}
            if rng.random() < 0.7:
                contacto["web"] = fake.url()
            ficha["contacto"] = contacto

        # Inclúe estes datos só nalgúns documentos para variar a súa estrutura
        if rng.random() < 0.75:
            ficha["admite_cans"] = rng.choice([True, False])

        # Se hai información de bicicletas, xera tamén a capacidade do garaxe
        if rng.random() < 0.7:
            ten_garaxe = rng.choice([True, False])
            ficha["bicicletas"] = {
                "garaxe": ten_garaxe,
                "prazas": rng.randint(4, 20) if ten_garaxe else 0,
            }

        # Selecciona unha combinación de idiomas sen repeticións
        if rng.random() < 0.65:
            ficha["idiomas"] = rng.sample(idiomas_posibles, rng.randint(2, 4))

        # As opinións son exclusivas dos privados e poden non aparecer
        if not publico and rng.random() < 0.6:
            ficha["opinions"] = [
                {
                    "autor": f"{fake.first_name()[0]}.",
                    "nota": rng.randint(3, 5),
                    "texto": rng.choice(textos_opinion),
                }
                for _ in range(rng.randint(1, 3))
            ]

        # Engade a ficha completa á lista
        fichas.append(ficha)

    return fichas


# ------------------------------------------------------------------ carga
def carga_postgres(albergues, peregrinos, reservas):
    """TODO: crea as táboas (ou usa un script SQL de inicio) e insire os datos."""

    
    pendente("carga_postgres")


def carga_mongo(fichas):
    """TODO: garda as fichas nunha colección de MongoDB."""
    pendente("carga_mongo")


# ------------------------------------------------------------------ main
def mostra(titulo, filas, cantas=2):
    print(f"\n{titulo}: {len(filas)}")
    for f in filas[:cantas]:
        print(f"  {f}")


def main():
    ap = argparse.ArgumentParser(description="Xera e carga datos de proba de Camiño Aberto")
    ap.add_argument("--albergues", type=int, default=40)
    ap.add_argument("--peregrinos", type=int, default=1500)
    ap.add_argument("--reservas", type=int, default=5000)
    ap.add_argument("--semente", type=int, default=42, help="mesma semente → mesmos datos")
    ap.add_argument("--desde", type=date.fromisoformat, default=date(2027, 5, 1),
                    help="primeira noite da tempada (AAAA-MM-DD)")
    ap.add_argument("--dias", type=int, default=30, help="número de noites da tempada")
    ap.add_argument("--sen-carga", action="store_true", help="xera e mostra, pero non carga nada")
    args = ap.parse_args()

    rng = random.Random(args.semente)
    fake = Faker("es_ES")
    # TODO: Faker tamén ten a súa propia semente. Sen ela, os nomes cambian en cada execución.

    print(f"Semente {args.semente} · tempada {args.desde} + {args.dias} noites")
    albergues = xera_albergues(args.albergues, rng)
    peregrinos = xera_peregrinos(args.peregrinos, rng, fake)
    reservas = xera_reservas(args.reservas, albergues, peregrinos, args.desde, args.dias, rng)
    fichas = xera_fichas(albergues, rng, fake)

    mostra("Albergues", albergues)
    mostra("Peregrinos", peregrinos)
    mostra("Reservas", reservas)
    mostra("Fichas", fichas, 1)

    if not args.sen_carga:
        carga_postgres(albergues, peregrinos, reservas)
        carga_mongo(fichas)


if __name__ == "__main__":
    main()
