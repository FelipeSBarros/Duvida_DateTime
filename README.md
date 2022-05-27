## Tentando entender a relação datetime com e sem `timezone` entre SQLAlchemy e Postgres

Pessoal, em um projeto que estou desenvolvendo comecei a ter alguns problemas com os dados de data e hora armazenados no banco de dados Postgres e manipulados no python. Basicamente, os dados são manipulados em python com o pacote `datetime`, salvos no banco de dados usando `SQLAlchmey`.

Tentei reproduzir o que tenho encontrado e tantando expandir o problema, criai uma tabela `DateTimeTable` com quatro campos: dois campos [`DateTime()`](https://docs.sqlalchemy.org/en/14/core/type_basics.html#sqlalchemy.types.DateTime), um deles com o parâmetro [`timezone=True`](https://docs.sqlalchemy.org/en/14/core/type_basics.html#sqlalchemy.types.DateTime.params.timezone), e outros dois campos de texto para ter a documentação do valor enviado com [`isoformat()`](https://docs.python.org/3/library/datetime.html#datetime.datetime.isoformat).  

### TL/DR  

Ao trabalhar com objetos datetime, salva-los num banco de dados postgres, em campo DateTime, e resgata-los com SQLAlchemy, pudo perceber que algumas conversoes sao feitas. Fiquei perdido sem entender e que momento essas conversoes xacontecem nem como controla-las. Afinal, a pergunta e:  

Como evitar ao máximo as conversões entre o objeto `datetime`, o que está salvo no banco de dados e o que é resgatado pelo SQLAlchemy?

Segue uma reprodução do problema:

## Preparando ambiente de desenvolvimento

```
mkdir datetime
cd datetime
python -m venv .venv
source .venv/bin/activate
pip intall --upgrade pip
pip install -r requirements.txt
```

### Docker com Postgres

```commandline
docker pull postgres

docker run --name teste_datetime -e POSTGRES_PASSWORD=password -p 0.0.0.0:5433:5432 -d postgres

# confirmando existencia
docker container ps
#CONTAINER ID   IMAGE      COMMAND                  CREATED         STATUS         PORTS                    NAMES
#c77150c506a8   postgres   "docker-entrypoint.s…"   6 seconds ago   Up 5 seconds
```

#### Identificando timezone do conteiner/base de dados

```commandline
psql -h localhost -U postgres -p 5433
show timezone;
# TimeZone 
#----------
# Etc/UTC
#(1 row)

```
Se faço um select now(), ele me dá a data e hora com a info de timezone (+00):

```commandline
select now();
#              now              
#-------------------------------
# 2022-05-27 15:36:59.903336+00
#(1 row)


```

Agora confirmando o timezone de onde esta rodando o python:

```python
from datetime import datetime
datetime.now().astimezone().tzinfo
#datetime.timezone(datetime.timedelta(days=-1, seconds=75600), '-03')
```

Ou seja o timezone é -03 em relação ao UTC.

Crio uma tabela `DateTimeTable` com campos `DateTime()`, com o parâmetro `timeZone` como verdadeiro e falta (respectivamente, colunas `date_time_tz_aware` e `date_time_naive`):  

```python
import json

from sqlalchemy import Integer, DateTime, Text
from sqlalchemy import create_engine, Column
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()


BD_USERNAME = "postgres"
BD_PASSWORD = "password"
BD_HOST = "localhost"
BD_PORT = "5433"
BD_NAME = "postgres"


def db_connect():
    return create_engine(
        f"postgresql+psycopg2://{BD_USERNAME}:{BD_PASSWORD}@{BD_HOST}:{BD_PORT}/{BD_NAME}",
        json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False, default=str),
    )


def create_table(engine):
    Base.metadata.create_all(engine)


class DateTimeTable(Base):
    __tablename__ = "datetime"

    id = Column(Integer, primary_key=True)
    date_time_tz_aware = Column(DateTime(timezone=True))
    isoformat_tz_aware = Column(Text)
    date_time_naive = Column("datetime_naive", DateTime(timezone=False))
    isoformat_naive = Column(Text)


engine = db_connect()
create_table(engine)

```

datetime com (aware) e sem (naive) informação de `timezone`: 

```python
import pytz
from datetime import datetime
from sqlalchemy.orm import sessionmaker


engine = db_connect()
Session = sessionmaker(bind=engine)
session = Session()


BR_TIME_ZONE = pytz.timezone("America/Sao_Paulo")

#naive = datetime.now()
naive = datetime(2022, 5, 27, 12, 30, 0, 0)
aware = naive.replace(tzinfo=BR_TIME_ZONE)

record = DateTimeTable(
    date_time_tz_aware=aware,
    isoformat_tz_aware=f"{aware.isoformat()}",
    date_time_naive=naive,
    isoformat_naive=f"{naive.isoformat()}"
)

session.add(record)
session.commit()
session.close()
```

No banco de dados já começo a ter alguns resultados estranhos:

```
id  date_time_tz_aware    iso_format_tz_aware    date_time_naive    isofomat_naive
1	2022-05-27 12:36:00.000 -0300	2022-05-27T12:30:00-03:06	2022-05-27 12:30:00.000	2022-05-27T12:30:00
```

Reparem que no postgres:  

- com na coluna com `timezone=True`, o objeto tz aware tem seis minutos acrescidos. devria ser 12:30 e passou a ser 12:36; Me parece estranho que haja sido acrescido seis minutos... A informação de `timezone`, me parece correta: -0300... 
- A coluna `iso_format_tz_aware` possui o objeto tal qual como enviado. A unica novidade é que o `tmezone` não é apenas -3 horas. É -03 horas e 06 minutos. Até me chamou atenção pois olhando de novo o `timezone` da coluna `date_time_aware` é informado apenas `-0300`;
- `date_time_naive` e `isoformat_naive` tem os dados armazenados corretamente.

Ao acessar esses dados usnado o SQLAlchemy, a bagunça aumenta:

```python
session=Session()
for row in session.query(DateTimeTable).all():
    print(row.date_time_tz_aware, row.isoformat_tz_aware, row.date_time_naive, row.isoformat_naive)
# id  date_time_tz_aware    iso_format_tz_aware    date_time_naive    isofomat_naive
# 2022-05-27 15:36:00+00:00 2022-05-27T12:30:00-03:06 2022-05-27 12:30:00 2022-05-27T12:30:00
```

Reparem que no python, acessando os dados pelo sqlalchemy:  

- Na coluna `date_time_tz_aware`, o objeto tem três horas e seis minutos acrescidos e o `timezone` em utc (+00:00). Vale lembrar que o `timezon` informado no banco de dados era de `-0300`, sem incluir mudanças de minutos;  
- Na coluna `iso_format_tz_aware` possui o objeto tal qual como enviado, mantendo a novidade do `tmezone` com -3 horas e 06 minutos;
- `date_time_naive` e `isoformat_naive` tem os dados retornados assim como esão no banco de dados.

Para aumentar um pouco a bagunça, inseri em ambas colunda s o objeto datetime com `tzinfo`:

```python
record2 = DateTimeTable(
    date_time_tz_aware=aware,
    isoformat_tz_aware=f"{aware.isoformat()}",
    date_time_naive=aware,
    isoformat_naive=f"{aware.isoformat()}"
)
session.add(record2)
session.commit()

```

No banco de dados, tenho:

```
# id  date_time_tz_aware    iso_format_tz_aware    date_time_naive    isofomat_naive
# 2	2022-05-27 12:36:00.000 -0300	2022-05-27T12:30:00-03:06	2022-05-27 15:36:00.000	2022-05-27T12:30:00-03:06
```

Reparem que:

- Nas colunas `tz_aware` nada mudou do exemplo anterior. OK.
- Na coluna `naive`, passo a ter o objeto alterado, sendo acrescido 3 horas e 6 minutos;

```python
# date_time_tz_aware    iso_format_tz_aware    date_time_naive    isofomat_naive
# 2022-05-27 15:36:00+00:00 2022-05-27T12:30:00-03:06 2022-05-27 15:36:00 2022-05-27T12:30:00-03:06
```

Ao acessar tais dados pelo SQLAlchemy, a info do banco de dados é respeitada.

Aumentando ainda mais a bagunça III:
Insiro os dados naive, sem info de `timezone`, em todos os campos:

```python
# terceiro registro inserindo datetime naive sempre
record3 = DateTimeTable(
    date_time_tz_aware=naive,
    isoformat_tz_aware=f"{naive.isoformat()}",
    date_time_naive=naive,
    isoformat_naive=f"{naive.isoformat()}"
)
session.add(record3)
session.commit()

session.close()

```

No banco de dados, tenho:

```python
# date_time_tz_aware    iso_format_tz_aware    date_time_naive    isofomat_naive
# 3 	2022-05-27 09:30:00.000 -0300	2022-05-27T12:30:00	2022-05-27 12:30:00.000	2022-05-27T12:30:00
```

Percebam que:

- Na coluna `tz_aware` o campo de hora possui tres horas descontada, e a info de timezone e de -0300.
- Na coluna `naive`, os objetos possuem os valores respeitados;

Acessando so dados pelo SQLAlchemy, passo a ter:

```python
# date_time_tz_aware    iso_format_tz_aware    date_time_naive    isofomat_naive
# 2022-05-27 12:30:00+00:00 2022-05-27T12:30:00 2022-05-27 12:30:00 2022-05-27T12:30:00
```

- Na coluna `tz_aware`, a hora conforme salvo no banco, mas com info de `timezone` para utx (+00:00:00)
- Na coluna `naive` também, mas, como esperado sem a info de `timezone`;

Estou bem perdido em como trabalhar com esses dados. Como evitar ao máximo as conversões entre o objeto `datetime`, o que está salvo no banco de dados e o que é resgatado pelo SQLAlchemy?