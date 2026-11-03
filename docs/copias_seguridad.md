# Copias de seguridade e restauración

## Obxectivo

Implementar un sistema de copias de seguridade para PostgreSQL e MongoDB mediante un script Bash, garantindo que os datos poidan recuperarse en caso de perda.

## Ferramentas utilizadas

- **PostgreSQL:** `pg_dump` para crear copias en formato personalizado e `pg_restore` para recuperalas.
- **MongoDB:** `mongodump` para crear arquivos comprimidos e `mongorestore` para recuperar os documentos.
- **Docker Compose:** execución das ferramentas dentro dos contedores.
- **Bash:** automatización das operacións mediante `src/copia.sh`.

## Execución

Desde a raíz do proxecto:

### Crear copias

```bash
bash src/copia.sh backup
```

Tamén se pode executar sen argumentos:

```bash
bash src/copia.sh
```

Xéranse dous ficheiros no directorio `copias/`, identificados coa data e hora da execución:

```text
copias/
├── postgres_2026-11-03_19-30-21.dump
└── mongo_2026-11-03_19-30-21.archive.gz
```

O directorio `copias/` está excluído do control de versións mediante `.gitignore`.

### Restaurar nunha nova base de probas

```bash
bash src/copia.sh restaurar \
  copias/postgres_2026-11-03_19-30-21.dump \
  copias/mongo_2026-11-03_19-30-21.archive.gz
```

O script crea bases de datos de proba cun nome xerado automaticamente, sen modificar as bases orixinais.

### Restaurar nunha base de probas existente

```bash
bash src/copia.sh restaurar-en \
  albergues_proba_20261103_193733 \
  copias/postgres_2026-11-03_19-30-21.dump \
  copias/mongo_2026-11-03_19-30-21.archive.gz
```

Este modo permite recuperar unha base de probas existente substituíndo os obxectos incluídos na copia. Non permite indicar a base orixinal `albergues` como destino.

## Proba de borrado e recuperación

Realizouse unha simulación de perda de datos sobre bases de probas independentes.

1. Restauráronse as copias de PostgreSQL e MongoDB.
2. Elimináronse as reservas de PostgreSQL mediante `TRUNCATE TABLE reservas`.
3. Elimináronse os documentos de MongoDB mediante `deleteMany({})`.
4. Comprobouse que ambas coleccións de datos estaban baleiras.
5. Restauráronse novamente as copias mediante `pg_restore` e `mongorestore`.
6. Consultáronse os rexistros recuperados.

### Resultados

| Sistema | Antes do borrado | Despois do borrado | Despois da recuperación |
|---|---:|---:|---:|
| PostgreSQL — reservas | 20 | 0 | 20 |
| MongoDB — fichas_albergues | 3 | 0 | 3 |

**Resultado:** a recuperación foi satisfactoria en ambos sistemas, sen erros de restauración e sen modificar as bases de datos orixinais.

## Consideracións de seguridade

- As credenciais están configuradas mediante variables de contorno dos contedores.
- As copias almacénanse localmente e non se inclúen en Git.
- Os modos de restauración utilizan bases de probas para evitar sobrescrituras accidentais da información orixinal.
- As copias poden conter datos sensibles e deben almacenarse en localizacións protexidas.