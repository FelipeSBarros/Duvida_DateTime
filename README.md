## Tentando entender a relação datetime com e sem `timezone` entre SQLAlchemy e Postgres

**Última [atualização: 31/05](#update-1)**  
**Última [atualização: 1/06](#update-2)**  

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

### Update 1

Ao conversar com um colega, me foi informado que a forma como eu estava definido o `timezone` esatava equivocado. A única direção dada, por ele foi [essa pergunta no SOF](https://stackoverflow.com/questions/1379740/pytz-localize-vs-datetime-replace).
Os detalhes são um pouco confusos, mas esse comentário acho que indica onde estou errando na definição do `timezone` e o porquê:

>@MichaelWaterfall: pytz.timezone() may correspond to several tzinfo objects (same place, different UTC offsets, timezone abbreviations). tz.localize(d) tries to find the correct tzinfo for the given d local time (some local time is ambiguous or doesn't exist). replace() just sets whatever (random) info pytz timezone provides by default without regard for the given date (LMT in recent versions). tz.normalize() may adjust the time if d is a non-existent local time e.g., the time during DST transition in Spring (northern hemisphere) otherwise it does nothing in this case.

Então, como estou usando o `pytz` para definir um objeto de `timezone`, o `replace` não seria a forma correta, mas sim, o método `localize` do pórprio timezone. Reparem a diferença que isso fez:

```
BR_TIME_ZONE = pytz.timezone("America/Sao_Paulo")
naive = datetime(2022, 5, 27, 12, 30, 0, 0)
naive.replace(tzinfo=BR_TIME_ZONE)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=<DstTzInfo 'America/Sao_Paulo' LMT-1 day, 20:54:00 STD>)
BR_TIME_ZONE.localize(naive)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=<DstTzInfo 'America/Sao_Paulo' -03-1 day, 21:00:00 STD>)
```

Reparem que há uma diferença de seis minutos entre os objetos resultantes, sendo o retornado pelo `localize`, o correto (21 e 20:54).

Fiz mais um testepara entender se o problema é o método `replace` ou a forma como o `pytz` define o `timezone`:

```python
datetime(2022, 5, 27, 12, 30, 0, 0, tzinfo=BR_TIME_ZONE)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=<DstTzInfo 'America/Sao_Paulo' LMT-1 day, 20:54:00 STD>)
```

Mesmo passando o `timezone` do `pytz` como parâmetro `tzinfo`, a diferença de seis minutos segue (20:54). Ou seja, também não é a forma correta.

Ao salvar no banco de dados o objeto `aware` criado usando o `localize`, os dados foram, enfim, salvos de forma correta:

```python
# date_time_tz_aware    iso_format_tz_aware    date_time_naive    isofomat_naive
# 2022-05-27 12:30:00.000 -0300	2022-05-27T12:30:00-03:00	2022-05-27 12:30:00.000	2022-05-27T12:30:00
```

OK, um problema, resolvido. Os dados de datetime estão sendo salvos de forma correta no banco de dados e com a inforação do `timezone`. Mas a consulta feita pelo SQLAlchemy, retorna o dado convertido em UTC. Fiquei nevegando por várias perguntas no SOF, e comecei a refletir sobre isso.
Vi, em uma delas que o SQLAlchemy por padrão retorna os dados em UTC, mesmo. A pergunta que me fiz foi: Por que?
Com o tempo mudei a pergunta para: Porque guardar a iformação de timezone junto? Se o sistema estiver rodando numa única timezone, podemos usar o formato naive. Então, comecei a suspeitar que a ideia de salvar os dados com a info de timezone, tenha a ver com a possibilidade de registros terem diferentes timezones.
Então, comecei a desconfiar que o SQLAlchemy retorna um UTC já padronizando, todos os registros, para um único `timezone`, o UTC.
Resolvi, então fazer um teste: selecionei um `timezone` aleatório do `pytz` e salvei no banco:

```python
BRU_TIME_ZONE = pytz.timezone("Asia/Brunei")
aware = BRU_TIME_ZONE.localize(naive)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=<DstTzInfo 'Asia/Brunei' +08+8:00:00 STD>)
```

No banco de dados ficou:

```python
# date_time_tz_aware    iso_format_tz_aware    date_time_naive    isofomat_naive
# 2022-05-27 01:30:00.000 -0300	2022-05-27T12:30:00+08:00	2022-05-27 12:30:00.000	2022-05-27T12:30:00
```

Pronto, **agora é que eu não entendi nada.** Espearava ver o registro com a info do `timezone` (+0800), mas não. O SQLAlchemy mandou para o banco com o `timezone` -0300.

Pois, se eu posso gardar diferentes registros com diferentes `timezones`, pode ser que o SQLAlchemy já faça a homogeneização ao UTC por padrão para facilitar a vida do usuário, que terá que converter apenas de UTC ao `timezone` desejado...

Sigo perdido.

Mais alguns pontos: fui assistir [à live de python sobre `datetime`, feita há algumas semanas](https://youtu.be/BImF-dZYass?t=3948). Vi que, o [@dunossauro](https://twitter.com/dunossauro) indica a definição de `timezone` usando [`timedelta`](https://docs.python.org/3/library/datetime.html#timedelta-objects).

Vamos testar, então: 

```python
from datetime import timezone, timedelta

# BR_TIME_ZONE = pytz.timezone("America/Sao_Paulo")
BR_TIME_ZONE = timezone(timedelta(hours=-3))
```

O processo de definição do `timezone`, seguiu o mesmo, usando o [`localize`]().

```python
# date_time_tz_aware    iso_format_tz_aware    date_time_naive    isofomat_naive
# 2022-05-27 12:30:00.000 -0300	2022-05-27T12:30:00-03:00	2022-05-27 12:30:00.000	2022-05-27T12:30:00
```

Bom, parece que essa forma também persiste os dados de forma correta. Gracias, [@dunossauro](https://twitter.com/dunossauro)!

Agora ficam as seguintes dúvidas:

* Por que objetos em outro timezone são persistidos com o timezone -0300?
> Por incrível que pareça, quando executo `show timezone;` no psql, tenho o retorno informado no início do texto (UTC). Mas ao executr numa gui, [DBeaver]() tive o timezone de Buenos Aires, retornado: America/Argentina/Buenos_Aires. Logo, presumo que esse é o timezone do banco de dados e por isso ele está ssumindo -0300 para todos os registros.
* É possível ter registros em diferentes timezones no postgres?  
* Por que o SQLAlchemy sempre retorna os dados em UTC?  

Ainda falta:
* explorar a sugestão do [cuducos](https://twitter.com/cuducos): identificar como a *query* é feita pelo SQLAlchemy, tanto para salvar os dados, como para resgatar-los.

A saga continua...

### Update 2

Nem fiz o commit segui "encucado" do o fato de o postgres salvar todos os registros em timezone -0300.
decidi acessar o psql e confirmar o timezone. Fiz o mesmo, usando uma GUI (DBEAVER) e: cada um apresenta um timezone diferente. No psql, UTC e na GUI -3.
Fiz as consultas que estive apresetando aqui (que eram provenientes do visualizador DBeaver) pelo psl e eis que todos os registro são salvos em UTC, no banco de dados!
```python
psql -h localhost -U postgres -p 5433 postgres
select * from datetime
```
:warning: não reparem a quantidade de registros...

| id \|      date_time_tz_aware       \|        isoformat_tz_aware        \|       datetime_naive       \|      isoformat_naive 	|
|---	|
| ----+-------------------------------+----------------------------------+----------------------------+---------------------------- 	|
| 1 \| 2022-05-27 15:49:15.613346+00 \| 2022-05-27T12:43:15.613346       \| 2022-05-27 15:49:15.613346 \| 2022-05-27T12:43:15.613346 	|
| 2 \| 2022-05-27 15:49:15.613346+00 \| 2022-05-27T12:43:15.613346-03:06 \| 2022-05-27 12:43:15.613346 \| 2022-05-27T12:43:15.613346 	|
| 3 \| 2022-05-27 15:36:00+00        \| 2022-05-27T12:30:00-03:06        \| 2022-05-27 12:30:00        \| 2022-05-27T12:30:00 	|
| 4 \| 2022-05-27 15:36:00+00        \| 2022-05-27T12:30:00-03:06        \| 2022-05-27 15:36:00        \| 2022-05-27T12:30:00-03:06 	|
| 5 \| 2022-05-27 12:30:00+00        \| 2022-05-27T12:30:00              \| 2022-05-27 12:30:00        \| 2022-05-27T12:30:00 	|
| 6 \| 2022-05-27 15:30:00+00        \| 2022-05-27T12:30:00-03:00        \| 2022-05-27 12:30:00        \| 2022-05-27T12:30:00 	|
| 7 \| 2022-05-27 15:30:00+00        \| 2022-05-27T12:30:00-03:00        \| 2022-05-27 12:30:00        \| 2022-05-27T12:30:00 	|
| 9 \| 2022-05-27 04:30:00+00        \| 2022-05-27T12:30:00+08:00        \| 2022-05-27 12:30:00        \| 2022-05-27T12:30:00 	|
| 8 \| 2022-05-27 04:30:00+00        \| 2022-05-27T12:30:00+08:00        \| 2022-05-27 12:30:00        \| 2022-05-27T12:30:00 	|

Ou seja, o postgres recebe o dado em diferentes timezones e converte tudo para UTC. O que estava em +8, foi convertido a UTC, tbm.

Isso me fez lembrar da documentação do postgres:

> For timestamp with time zone, the internally stored value is always in UTC (Universal Coordinated Time, traditionally known as Greenwich Mean Time, GMT). An input value that has an explicit time zone specified is converted to UTC using the appropriate offset for that time zone. If no time zone is stated in the input string, then it is assumed to be in the time zone indicated by the system's TimeZone parameter, and is converted to UTC using the offset for the timezone zone.
> [fonte](https://www.postgresql.org/docs/current/datatype-datetime.html)

Isso aí foi tema de discussão com meu chefe...

voltando aos pontos levantados antes:
Agora ficam as seguintes dúvidas:

* Por que objetos em outro timezone são persistidos com o timezone -0300?
> Na verdade no postgres os dados são persistidos em UTC. Seja qual for o `timezone` do objeto o mesmo é corretamente convertido.
* É possível ter registros em diferentes timezones no postgres?  
> Não, a menos que se mude nas configurações do banco de dados. Mas todos sao devidamente convertidos  a UTC.
* Por que o SQLAlchemy sempre retorna os dados em UTC?  
> Pelo visto nao e o SQLAlchemy que faz isso. Ele apenas retorna os dados tal qual estao. Agora fica a pergunta:
> A conversao de timezone e feita pelo sqlalchemy ou pelo postgres. A principio me parece ser o proprio postgres. Talvez essa duvida seja resolvida explorando a query de inserçao.  
