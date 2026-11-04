## Probas de funcionamento e medicións

Realizáronse distintas probas para comprobar o correcto funcionamento da infraestrutura, a coherencia dos datos e o comportamento do sistema de reservas.

### 1. Xeración e carga de datos

- Xeración reproducible comprobada utilizando a mesma semente (`7`) en dúas execucións.
- PostgreSQL: 3 albergues, 15 peregrinos e 20 reservas.
- MongoDB: 3 fichas de albergues.
- Redis: 48 contadores de dispoñibilidade inicializados a partir de PostgreSQL.

### 2. Proba de sobreventa

Executáronse 30 intentos de reserva simultáneos para un albergue con 3 prazas dispoñibles.

| Resultado | Valor |
|---|---:|
| Intentos | 30 |
| Reservas confirmadas | 3 |
| Reservas rexeitadas | 27 |
| Reservas en PostgreSQL | 3 |
| Prazas restantes en Redis | 0 |

**Resultado:** proba superada, sen sobreventa e mantendo a coherencia entre PostgreSQL e Redis.

### 3. Recuperación ante erros de PostgreSQL

Simulouse unha reserva cun peregrino inexistente para provocar un erro de clave foránea.

- Prazas en Redis antes do intento: 22.
- PostgreSQL rexeitou a inserción.
- Prazas en Redis despois do erro: 22.

**Resultado:** o mecanismo de compensación devolveu correctamente a praza descontada.

### 4. Caché de Redis

Comprobouse unha consulta de dispoñibilidade para o Camiño Francés o 01/05/2027.

- TTL inicial: 30 segundos.
- TTL despois de dous segundos: 28 segundos.
- O resultado almacenado en caché coincidiu co de PostgreSQL.

Tamén se comprobou a invalidación da caché despois dunha reserva confirmada:

- Dispoñibilidade inicial: 3 prazas.
- Dispoñibilidade despois da reserva: 2 prazas.
- A entrada de caché anterior eliminouse correctamente.
- A nova consulta devolveu os mesmos resultados ca PostgreSQL.

### 5. Comparación de rendemento

Medíronse os tempos medios de 100 consultas de dispoñibilidade para o Camiño Francés o 01/05/2027.

| Sistema | Tempo medio |
|---|---:|
| PostgreSQL | 13,599 ms |
| Redis con caché | 8,003 ms |

Nesta proba Redis foi aproximadamente **1,70 veces máis rápido**, cunha redución do tempo medio do **41,2 %**.

Os resultados son orientativos, xa que se empregou un conxunto pequeno de datos e os tempos dependen tamén da comunicación cos contedores.

### 6. Consumo de recursos

Medición puntual mediante `docker stats --no-stream`, cos contedores principalmente en repouso.

| Contedor | CPU | Memoria RAM |
|---|---:|---:|
| MongoDB | 0,53 % | 319,7 MiB |
| PostgreSQL | 0,00 % | 49,48 MiB |
| Redis | 0,27 % | 11,79 MiB |

MongoDB presentou o maior consumo de memoria nesta medición, mentres que Redis foi o servizo máis lixeiro.

### 7. Copias de seguridade

Comprobouse o funcionamento do script `src/copia.sh` para crear copias de PostgreSQL e MongoDB e restauralas en bases de proba.

Simulouse unha perda de datos eliminando os rexistros e recuperándoos posteriormente:

| Datos | Antes | Despois do borrado | Despois da restauración |
|---|---:|---:|---:|
| Reservas PostgreSQL | 20 | 0 | 20 |
| Fichas MongoDB | 3 | 0 | 3 |

**Resultado:** recuperación satisfactoria nos dous sistemas sen modificar as bases de datos orixinais. O procedemento detállase en `docs/copias_seguridad.md`.