# P1 · Sistema de Reservas de Albergues: Camiño Aberto

Este proxecto implementa a infraestrutura de datos dun sistema de reservas para a rede de albergues Camiño Aberto, combinando tecnoloxías relacionais, documentais e bases de datos en memoria para acadar alta dispoñibilidade, integridade e rendemento.

## 1. Arquitectura do Sistema

A solución divídese en tres sistemas principais, cada un optimizado para un propósito específico dentro do fluxo de datos (despregados con Docker Compose):

| Sistema | Función principal | Xustificación |
| :--- | :--- | :--- |
| **PostgreSQL 17** | Datos relacionais (albergues, peregrinos, reservas). | Garantiza a integridade referencial, o cumprimento ACID para as transaccións e un esquema ríxido para datos troncais. |
| **Redis 7.4** | Caché de consultas e xestión de contadores. | Permite validar a dispoñibilidade e facer reservas de xeito atómico en memoria de forma case instantánea, evitando asóbas na base principal. |
| **MongoDB 8.0** | Fichas detalladas dos albergues. | O seu esquema flexible permite gardar atributos dinámicos (opinións, servizos, garaxes) que varían enormemente entre albergues públicos e privados. |


> **Nota:** Cando se di que unha operación é "atómica" significa que se executa como un bloque único e indivisible: ou se completa totalmente ou non se fai, sen que ningún outro proceso poida interrumpila ou cortarse no medio.

## 2. Decisións de Diseño

### Estrutura de Datos en MongoDB (Esquema Flexible)
O xerador de datos (`src/xera_datos.py`) constrúe documentos dinámicos dependendo do tipo de albergue:
- **Albergues públicos:** conteñen información básica (nome, camiño, servizos, horario de apertura/peche e titularidade).
- **Albergues privados:** engaden campos opcionais e variables estruturalmente, como `contacto` (teléfono, web), `admite_cans`, `bicicletas` (garaxe e prazas), idiomas e un array de `opinions` (con autor, nota e texto). Isto xustifica plenamente o uso dunha base de datos NoSQL documental.

### Xestión en Redis (Claves, Atomicidade e Caché)
- **Contadores de prazas:** Emprégase o patrón de claves `albergue:dispo:{id_albergue}:{data}`. Cando chega unha solicitude, execútase un script Lua (`_DECREMENTAR_SE_DISPONIBLE`) que comproba e resta as prazas nunha única operación atómica, impedindo calquera sobreventa por condicións de carreira.
- **Caché de dispoñibilidade:** As consultas frecuentes gárdanse na caché usando o padrón `cache:dispo:{data}:{camino}`.
- **Tempo de vida (TTL):** Definiuse un `TTL` de **30 segundos** para a caché. Este valor considérase o punto de equilibrio óptimo: é o suficientemente longo para absorber picos de tráfico concorrente (ex. usuarios consultando a dispoñibilidade á mesma hora), pero o suficientemente curto para evitar mostrar datos obsoletos de prazas durante demasiado tempo. Ademais, impídese a lectura de datos falsos mediante a función `invalidar_cache_noite()` que borra a caché específica cando se confirma unha reserva nova.

## 3. Requisitos e Posta en Marcha

1. Crea e activa unha contorna virtual de Python, e instala as dependencias:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # En Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copia o ficheiro de variables de contorno e axusta os contrasinais se o desexas:
    ```bash
    cp .env.example .env
    ```

3. Inicia os contenedores mediante Docker Compose:
    ```bash
    docker compose up -d postgres redis mongo
    ```

*(Opcional: pódese acceder á interfaz Adminer a través do porto 8080).*

## 4. Xeración e Carga de Datos

O sistema inclúe un xerador de datos reproducible mediante a fixación dunha semente. Este paso limpará as bases de datos (PostgreSQL e MongoDB) e cargará o estado inicial:

```bash
python -m src.xera_datos --albergues 40 --peregrinos 1500 --reservas 5000 --semente 42
```

- Pódese engadir o flag `--sen-carga` para visualizar os datos na terminal sen inserilos nas bases de datos.

## 5. Aplicación: Probas e Medicións

Unha vez cargado o estado inicial, o sistema de reservas pódese probar utilizando o punto de entrada principal `app.py`.

### Inicialización dos contadores
Sincroniza os contadores de Redis a partir do estado actual en PostgreSQL:

```bash
python app.py inicializar
```

### Proba de Sobreventa
Simula un escenario de alta concorrencia onde múltiples fíos intentan reservar prazas simultaneamente nun albergue con capacidade limitada, poñendo a proba o script atómico de Redis:

```bash
python app.py probar-sobreventa --prazas 3 --intentos 30
```

- **Resultado esperado:** Só se confirmarán 3 reservas. As bases de datos PostgreSQL e Redis amosarán total coherencia sen rexistrar sobreventas.

### Medición de Rendemento (PostgreSQL vs Redis)
Compara a latencia dunha consulta directa á base relacionacional fronte ao acceso ao sistema de caché en Redis:

```bash
python app.py medir --repeticions 100
```

*Os resultados demostran que a obtención desde a caché de Redis (en milisegundos) é unha orde de magnitude máis rápida ca o cruzamento de táboas nativo en PostgreSQL.*

### Consumo de Recursos dos Contedores
Medicións obtidas mediante `docker` stats en estado de repouso/carga moderada:

| Contedor | CPU % | Memoria (Uso / Límite) | Mem % |
| :--- | :--- | :--- | :--- |
| `postgres` | ~0.15% | ~45 MiB / 15.5 GiB | ~0.28% |
| `mongo` | ~0.30% | ~90 MiB / 15.5 GiB | ~0.56% |
| `redis` | ~0.10% | ~15 MiB / 15.5 GiB | ~0.09% |

## 6. Copias de Seguridade e Restauración
O proxecto implementa un sistema de copias de seguridade automatizado para PostgreSQL e MongoDB mediante o script `src/copia.sh`.

### Crear copias

```bash
src/copia.sh backup
```

Xéranse dous ficheiros comprimidos e identificados por data no directorio `copias/` (ex: `postgres_YYYY-MM-DD_HH-MM-SS.dump` e `mongo_YYYY-MM-DD_HH-MM-SS.archive.gz`).

### Restaurar nunha nova base de probas

```bash
src/copia.sh restaurar copias/<ficheiro_pg>.dump copias/<ficheiro_mongo>.archive.gz
```

Crea unhas bases de datos clons cun nome xerado automaticamente para validar a integridade da copia sen alterar a información de produción.

### Restaurar nunha base de probas existente

```bash
src/copia.sh restaurar-en albergues_proba_20261103_193733 copias/<ficheiro_pg>.dump copias/<ficheiro_mongo>.archive.gz
```

### Simulación de Borrado e Recuperación
Levouse a cabo unha proba de desastre borrando táboas completas en bases clonadas:

1. Executouse `TRUNCATE TABLE reservas` (PostgreSQL) e `deleteMany({})` (MongoDB).

2. O reconto caeu de 20 reservas a 0, e de 3 fichas a 0.

3. Executouse a restauración vía `pg_restore` e `mongorestore` chamados polo script de recuperación.

4. Resultado: Os datos foron restaurados por completo de forma satisfactoria na base test (20 reservas, 3 fichas), evidenciando a integridade das copias e o éxito do procedemento.

## 7. Uso da Intelixencia Artificial
Durante o desenvolvemento deste proxecto, utilizáronse asistentes baseados en IA (como Gemini/ChatGPT) como apoio en labores de:

- Resolución de dúbidas sobre a sintaxe do script Lua para o decremento atómico en Redis.

- Elaboración e revisión de scripts para facilitar a interacción cos contedores de Docker durante as copias de seguridade.

- Estruturación formal e revisión gramatical deste documento README.