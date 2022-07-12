# Entendendo a fundo a relação datetime com e sem *time zone* entre SQLAlchemy e PostgreSQL

Há algum tempo comecei a perceber um "comportamento estranho" relacionado aos dados de data e hora num sistema que estava desenvolvendo. Minha reação inicial, praticamente um instinto de sobrevivencia, foi de simplemente resolver a situação contornando o problema. Mas chegou um momento que precisei entender a origem do mesmo. Mais uma vez tive que fazer um exercício de seguir/isolar o problema que me assombrava ([veja outros artigos que produzi sobre bugs/comportamentos estranhos que observo]()) para tentar compreender o motivo da sua existencia. Esse processo tomou-me alguns dias e, claro, proporcionou alguns aprendizados.

Ainda que agora, tendo resolvido e entendido as causas e origens desse comportamento, tudo parece óbvio, decidi compartilhar um pouco deste processo, pois nessa busca por soluções não encontrei nada que me ajudasse de forma objetiva.

Indice:  
1. [Contextualizando o sistema](#Contextualizando-o-sistema)
2. [Reproduzindo comportamentos estranhos](#Reproduzindo-comportamentos-estranhos)
   1. [Resolvendo problema de definição de *time zone*](#Resolvendo-problema-de-definição-de-time-zone)
   1. [Resolvendo problema de definição de *time zone* com `timedelta`](#Resolvendo-problema-de-definição-de-time-zone-com-timedelta)
   1. [O mistério das consultas sendo retornadas em UTC e `-0300`](#O-mistério-das-consultas-sendo-retornadas-em-UTC-e--0300)
   1. [coluna naive e aware](#coluna-naive-e-aware)
3. [Preparando ambiente de desenvolvimento](#Preparando-ambiente-de-desenvolvimento)
3. [TL/DR](#tldr)

Criei um ambiente para reproduzir esses "comportamentos estranhos" ([há uma sessão sobre como preparar um ambiente para poder reproduzir esses códigos](#Preparando-ambiente-de-desenvolvimento)) e deixarei os trechos de códigos usados, para vocês poderem reproduzir os passos dados. Irei trabalhar em todos os exemplos com um mesmo objeto de data e hora (instância `DateTime`) mudando apenas o uso de *time zone*, para torná-los conscientes (*aware*) ou não (*naive*) (leia um pouco sobre isso [aqui](https://docs.python.org/3/library/datetime.html#aware-and-naive-objects)).

## Contextualizando o sistema

Antes de tudo, lhes resumo a parte que importa do sistema:  

O mesmo estava numa instância EC2 da AWS, com *time zone* UTC, e nele eu manipulava um dado de data e hora, usando o módulo python [`datetime`](https://docs.python.org/3/library/datetime.html), com *time zone* consciente (`aware`), transformando-os ao *time zone* do Brasil (-0300). Esse dado era, então, persistido no banco de dados [PostgreSQL](https://www.postgresql.org/), que estava numa instância da azure, também com *time zone* UTC. Os dados eram persistidos em duas colunas diferentes: uma coluna [DateTime com *time zone* consciente](https://www.PostgreSQLql.org/docs/current/datatype-datetime.html) e numa coluna de texto onde, além da data e hora em formato [iso](https://docs.python.org/3/library/datetime.html#datetime.date.isoformat), uma observação textual era adicionada (que não vem ao caso, agora). Mas é importante saber que tínhamos o mesmo dado de data e hora persistido como tal e como texto.  

Um detalhe não menos importante é o fato de eu estar usando o módulo [`pytz`](https://pythonhosted.org/pytz/) para definir o *time zone* do Brasil (`America/Sao_Paulo`), e o [SQLAlchemy](https://www.sqlalchemy.org/), para fazer a conexão com o banco de dados, commit e etc. Pensando em facilitar a minha vida estive usando o [DBeaver](https://dbeaver.io/), uma interface gráfica para gestão de banco de dados. Ou seja, usava o DBeaver para conectar ao banco de dados e observar o que estava sendo persistido sem precisar fazê-lo pelo [`psql`](https://www.postgresql.org/docs/current/app-psql.html).

## Reproduzindo comportamentos estranhos

Basicamente criei uma instância `datetime` ingênua (*naive*) em relação ao *time zone* e outra com *time zone* declarado ( consciente, *aware*). Criei uma instância da tabela persistindo cada dado nas suas respectivas colunas (consciente na coluna consciente e ingênuo na coluna ingênua) ([veja aqui sobre a criação do ambiente para reproduzir esses códigos](#Preparando-ambiente-de-desenvolvimento)).

```python
import pytz
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(
        f"postgresql+psycopg2://postgres:password@localhost:5432/postgres")

Session = sessionmaker(bind=engine)
session = Session()


BR_TIME_ZONE = pytz.timezone("America/Sao_Paulo")

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

Ao fazer o commit e consultar a base de dados, começa o terror e pânico:

Usando o DBeaver para acessar o registro criado (seja pela interface gráfica como pela query da GUI), observei que:

* O valor persistido na coluna consciente foi alterado em seis minutos (acrescidos). **Deveria ser 12:30 e passou a ser 12:36**, ao passo que a informação de *time zone* é apresentada de forma correta: `-0300`;  
* O dado da coluna `iso_format_tz_aware` possui a informação sem qualquer alteraçao. Ao passo que a *time zone* informada não é a esperada (`-0300`), mas `-03:06`. Lembrem-se que o *time zone* da coluna `date_time_aware` é informado apenas `-0300`;
* Os dados persistidos nos campos *time zone* ingênuos não apresentaram qualquer alteração.

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
| 1 | 2022-05-27 12:36:00.000 -0300 | 2022-05-27T12:30:00-03:06 | 2022-05-27 12:30:00.000 | 2022-05-27T12:30:00 |

Contudo, ao acessar esses dados usando o SQLAlchemy, a confusão aumenta:

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |  |
|-------------|---|---|---|---|---|
| 1| 2022-05-27 15:36:00+00:00 | 2022-05-27T12:30:00-03:06 | 2022-05-27 12:30:00 | 2022-05-27T12:30:00 |

Reparem que agora temos:  

* Na coluna `date_time_tz_aware`, o objeto tem três horas e seis minutos acrescidos e o *time zone* informado como UTC (`+00:00`).  
* Os dados das colunas `iso_format`, `date_time_naive` e `isoformat_naive` apresentam os dados assim como estão no banco de dados.

Comportamentos estanhos a serem resolvidos:
* O *time zone* deveria ser de `-0300`. **De onde veio os seis munitos a mais?**
* Afinal, o dado é persistido no banco de dados em UTC (como retornado pelo SQLAlchemy) ou no *time zone* informado no objeto *datetime* (como retornado pelo DBeaver)?

### Resolvendo problema de definição de *time zone*

Ao conversar com um colega, me foi informado que a forma como eu estava definido o *time zone* esatava equivocado. A única direção dada por ele foi [essa pergunta no SOF](https://stackoverflow.com/questions/1379740/pytz-localize-vs-datetime-replace).

Um comentário me chamou a atenção:

> @MichaelWaterfall: pytz.*time zone*() may correspond to several tzinfo objects (same place, different UTC offsets, *time zone* abbreviations). tz.localize(d) tries to find the correct tzinfo for the given d local time (some local time is ambiguous or doesn't exist). replace() just sets whatever (random) info pytz *time zone* provides by default without regard for the given date (LMT in recent versions). tz.normalize() may adjust the time if d is a non-existent local time e.g., the time during DST transition in Spring (northern hemisphere) otherwise it does nothing in this case.

Em tradução livre:

> pytz.*time zone*() pode corresponder a objetos com diferentes tzinfo (mesmo local, diferentes *offset* em relaçõ ao UTC). tz.localize(d) tenta encontrar o tzinfo correto para um dada hora local (algumas horas locais são ambiguas ou inexistentes). replace() apenas define qualquer informação de *time zone* por padrão sem se preocupar com a data. tz.normalize() deve ajustar a informação de tempo se o objeto d não possuir informação de hora local.

Como estou usando o `pytz` para definir um objeto de *time zone*, o [`replace`](https://docs.python.org/3/library/datetime.html#datetime.datetime.replace) não seria a forma correta, mas sim, o método [`localize`](http://pytz.sourceforge.net/index.html?highlight=localize) da pórpria instância `pytz.timezone`.

Vamos testar, então:

```python
BR_TIME_ZONE = pytz.timezone("America/Sao_Paulo")
naive = datetime(2022, 5, 27, 12, 30, 0, 0)
naive.replace(tzinfo=BR_TIME_ZONE)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=<DstTzInfo 'America/Sao_Paulo' LMT-1 day, 20:54:00 STD>)
BR_TIME_ZONE.localize(naive)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=<DstTzInfo 'America/Sao_Paulo' -03-1 day, 21:00:00 STD>)
```

Reparem a diferença que isso fez no parametro `tzinfo` da instância: há uma diferença de seis minutos entre os objetos resultantes.

Gracias, [@georgersilva](https://twitter.com/georgersilva)!

Fiz mais um teste para entender se o problema é o método `replace` ou a forma como o `pytz` define o *time zone*:

```python
datetime(2022, 5, 27, 12, 30, 0, 0, tzinfo=BR_TIME_ZONE)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=<DstTzInfo 'America/Sao_Paulo' LMT-1 day, 20:54:00 STD>)
```

Mesmo passando o *time zone* do `pytz` como parâmetro `tzinfo`, a diferença de seis minutos segue (20:54). Ou seja, também não seria a forma correta.

Na documentação do `localize`, há apenas a menção:

> Unfortunately using the tzinfo argument of the standard datetime constructors ‘’does not work’’ with pytz for many timezones.

Ao salvar no banco de dados o objeto `aware` criado usando o `localize`, os dados foram, enfim, salvos de forma correta:

| date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive | isofomat_naive |
|---|---|---|---|---|
| 2022-05-27 12:30:00.000 -0300 | 2022-05-27T12:30:00-03:00 | 2022-05-27 12:30:00.000 | 2022-05-27T12:30:00 | 2022-05-27T12:30:00 |

:heavy_check_mark: OK, um problema resolvido.  
:question: Mas ainda fica o mistério das conversões entre o dado acessado pelo DBeaver daquele acessado pelo SQLAlchemy. 

Mas enquanto estava tentando resolver esse segundo problema, o [@dunossauro](https://twitter.com/dunossauro) fez uma [ live de python sobre `datetime`](https://youtu.be/BImF-dZYass?t=3948). Fui assistir e vi que, ele indicou usarmos a definição de *time zone* usando [`timedelta`](https://docs.python.org/3/library/datetime.html#timedelta-objects). Me pareceu sensato. Vamos testar, então: 

### Resolvendo problema de definição de *time zone* com `timedelta`

```python
from datetime import timezone, timedelta

# BR_TIME_ZONE = pytz.timezone("America/Sao_Paulo")
BR_TIME_ZONE = timezone(timedelta(hours=-3))
datetime(2022, 5, 27, 12, 30, 0, 0, tzinfo=BR_TIME_ZONE)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=datetime.timezone(datetime.timedelta(days=-1, seconds=75600)))
datetime(2022, 5, 27, 12, 30, 0, 0).replace(tzinfo=BR_TIME_ZONE)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=datetime.timezone(datetime.timedelta(days=-1, seconds=75600)))
```

Reparem que agora não estamos mais usando uma instância [`TimeZone`]() do `pytz` e por isso não poderemos usar o método `localize()`. Com o timedelta, obtivemos os resultados esperados tanto informando passando o objeto no parâmetro `tzinfo` na criação da intância `datetime`, como ao usar o método `replace`.

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
|  | 2022-05-27 12:30:00.000 -0300 | 2022-05-27T12:30:00-03:00 | 2022-05-27 12:30:00.000 | 2022-05-27T12:30:00 |

Dessa forma também temos os dados persistidos corretamente e ainda nos poupa de usar o `pytz`. Gracias, [@dunossauro](https://twitter.com/dunossauro)!

### O mistério das consultas sendo retornadas em UTC e `-0300`

Só para refrescar a memória: Ao acessar os dados presistidos no banco de dados usando o DBeaver, os recebia com o *time zone* -0300, enquanto ao acessar pelo SQLAlchemy, os mesmos dados eram retornados em UTC +00:00.

Decidi acessar o banco e fazer as consultas apresentadas anteriormente pelo [psql](https://www.PostgreSQLql.org/docs/current/app-psql.html) e pelo DBeaver para confirmar:
1. o *time zone* da instancia do banco de dados, e;
2. o *time zone* dos dados persistidos;

#### Confirmando o *time zone* da instância do banco de dados

Executando o mesmo comando no `psql` e DBeaver para uma mesma instância de banco dados tive diferentes retornos:

```commandline
psql -h localhost -U postgres -p 5432 postgres

show timezone;
```

![](img/show_timezone_psql.png)

![](img/show_timezone_dbeaver.png)

Eis, então, que fica evidente: o mesmo banco de dados apresentando *time zone* diferentes de acordo com a ferramenta usada na conexao. 
Isso me fez lembrar da documentação do PostgreSQL que já havia lido, mas não tinha dado a devida atenção:

> For timestamp with time zone, the internally stored value is always in UTC (Universal Coordinated Time, traditionally known as Greenwich Mean Time, GMT). An input value that has an explicit time zone specified is converted to UTC using the appropriate offset for that time zone. If no time zone is stated in the input string, then it is assumed to be in the time zone indicated by the system's *time zone* parameter, and is converted to UTC using the offset for the *time zone* zone.
> [fonte](https://www.postgresql.org/docs/current/datatype-datetime.html)

Em traduçao livre:
> Para dados com informação de *time zone*, o valor armazenado estará sempre em UTC (também conhecido como GMT). Um valor de entrada que não tenha *time zone* declarado explicitamente será convertido a UTC usando o *time zone* indicado pelo sistema.

A partir disso, várias constatações:

* Os dados que possuem a informação de *time zone*, são convertidos a UTC. Os dado sem essa definiçao é entendido como já estando em UTC, logo não é convertido.
* O DBeaver identificou o *time zone* da minha máquina e ao retornar uma consulta ja convertia todos os dados considerando o *time zone* da minha maquina.
* Não é o SQLAlchemy que define como os dados serão resgatados, mas o PostgreSQL. Na verdade, essa definição é feita pela sessão de conexão com o banco de dados. Vejam:

```python
psql -h localhost -U postgres -p 5432 postgres

PostgreSQL= show time zone;
#  time zone
# ----------
#  Etc/UTC
# (1 row)

select * from datetime;
```

Com uma sessão (conexão) recém iniciada, o *time zone* é configurado para UTC (padrão), com os dados sendo retornados em UTC.

| id  |       date_time_tz_aware        |         isoformat_tz_aware         |        datetime_naive        |       isoformat_naive |
|-----|---|---|---|---|
| 1   |  2022-05-27 15:36:00+00         |  2022-05-27T12:30:00-03:06         |  2022-05-27 15:36:00         |  2022-05-27T12:30:00-03:06 |
| 2   |  2022-05-27 12:30:00+00         |  2022-05-27T12:30:00               |  2022-05-27 12:30:00         |  2022-05-27T12:30:00 |


Se, na mesma conexão, eu configuro o *time zone* para `America/Sao_Paulo`, e executo a mesma query, os dados na coluna com *time zone* consciente serão apresentados convertidos ao *time zone* definido na conexão (`-0300`).

```python
postgres=set timezone = 'America/Sao_Paulo';
#SET
postgres=show timezone;
#      timezone      
# -------------------
#  America/Sao_Paulo
# (1 row)


select * from datetime;
```

Eis que todos os dados são retornados em `-0300`:

| id  |       date_time_tz_aware        |         isoformat_tz_aware         |        datetime_naive        |       isoformat_naive |
|-----|---|---|---|---|
| 1   |  2022-05-27 12:36:00-03         |  2022-05-27T12:30:00-03:06         |  2022-05-27 12:30:00         |  2022-05-27T12:30:00 |
| 2   |  2022-05-27 09:30:00-03         |  2022-05-27T12:30:00               |  2022-05-27 12:30:00         |  2022-05-27T12:30:00 |

Tudo parece bem obvio, não? Mas uma coisa que foi fundamental para a minha confusão mental sobre esse comportamento: o fato de estar usando o DBeaver como interface gráfica para ver como os dados estavam armazenados no banco de dados. O DBeaver, em algum momento, identifica o *time zone* do sistema que o está executando e o usa na configuração da sessão. Com isso, ao olhar os mesmos dados pelo DBeaver, os via convertidos para a *time zone* do meu sistema e acreditava que os mesmos estavam sendo persistidos como tal no banco de dados. Ao acessar os dados pelo SQLAlchemy (que usa uma sessão padrão, sem configuração de *time zone*, logo em UTC) recebia os dados em UTC. Ficando sem entender o que nem como estava sendo persistido. 

:heacy_checkmark: Fica o aprendizado: O PostgreSQL irá retornar os dados de data e hora no *time zone* da sessão de conexão, que por padrão é UTC. Caso vc queira receber-los em outro *time zone*, basta definir usando o [`SET timezone`](https://www.postgresql.org/docs/current/sql-set.html), ou, se for usando o SQLAlchemy, você poderá fazê-lo usando o parâmetro [connect_args](https://docs.sqlalchemy.org/en/14/core/engines.html#sqlalchemy.create_engine.params.connect_args):  

```
engine = create_engine(..., connect_args={"options": "-c timezone=-3"})`
```

### coluna naive e aware

Ainda que me tenha tomado um tempo considerável resolução de todas essas dúvidas, não chegou a esgotar a minha paciência. Por isso, fiz mais alguns testes, para tentar entender, de vez, a diferneça entre usar ou não coluna com *time zone* consciente e ingênua no PostgreSQL.

Ainda que já esteja superada a dúvida sobre as diferenças entre DBeaver e SQLAlchemy, seguirei aresentando as consultas usando ambas ferramentas, pois isso nos ajudará a entender as consequências ao usar campo consciente ou ingênuo.  

#### Primeiro teste:

Inseri em ambos campos de `DateTime` (consciente e ingênuo), um objeto com *time zone* consciente:

```python
record = DateTimeTable(
    date_time_tz_aware=aware,
    isoformat_tz_aware=f"{aware.isoformat()}",
    date_time_naive=aware,
    isoformat_naive=f"{aware.isoformat()}"
)
session.add(record)
session.commit()
```

Ao fazê-lo, o PosgreSQL entenderá o *time zone* do dado e, como dito anterioemente, os perssitirá em UTC (logo, acrescentando tres horas). **Isso tanto para o campo consciente como para o campo ingênuo**. A diferença, contudo estará no resgate da informaçao por uma sessão em UTC ou em outro *time zone*:

Acessando esse dado pelo DBeaver (sessão com *time zone* configurado em -0300), tenho o valor do campo `aware` convertido ao *time zone* da sessão (-0300) e indicando o mesmo, ao passo que o valor persistido no campo `naive` se mantêm em formato UTC **e sem a indicaçao do *time zone* :**

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
| 2 | 2022-05-27 12:30:00.000 -0300 | 2022-05-27T12:30:00-03:00 | 2022-05-27 15:30:00.000 | 2022-05-27T12:30:00-03:00 |

Já pelo SQLAlchemy a informação persistida no campo *time zone* consciente é retornada respeitando o *time zone* da sessão (logo, *time zone* UTC) e no campo ingênuo, não há alteração.

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
| 2 | 2022-05-27 15:30:00+00:00 | 2022-05-27T12:30:00-03:00 | 2022-05-27 15:30:00 | 2022-05-27T12:30:00-03:00 |

#### Segundo teste:

Ao inserir em ambos campos, um objeto ingênuo, em relaçao ao *time zone*, o PostgreSQL entende que os mesmos já estão em UTC. Logo, ao acessá-los pelo DBeaver (sessao com *time zone* -0300), o valor no campo consciente apresenta o desconto de três horas com a informação de *time zone* -0300, e na coluna `naive`, os valores não são alterados.

```python
# terceiro registro inserindo datetime naive sempre
record = DateTimeTable(
    date_time_tz_aware=naive,
    isoformat_tz_aware=f"{naive.isoformat()}",
    date_time_naive=naive,
    isoformat_naive=f"{naive.isoformat()}"
)
session.add(record)
session.commit()

session.close()
```

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
| 2 | 2022-05-27 09:30:00.000 -0300 | 2022-05-27T12:30:00 | 2022-05-27 12:30:00.000 | 2022-05-27T12:30:00 |

Acessando so dados pelo SQLAlchemy, tanto a couna consciente como a ingênua apresentam o mesmo valor. Contudo, no campo cosnceitne, a informação do *time zone* é persistido (+00:00:00).

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
| 2 | 2022-05-27 12:30:00+00:00 | 2022-05-27T12:30:00 | 2022-05-27 12:30:00 | 2022-05-27T12:30:00 |

## Preparando ambiente de desenvolvimento

```
mkdir datetime
cd datetime
python -m venv .venv
source .venv/bin/activate
pip intall --upgrade pip
pip install -r requirements.txt
```

### Docker com PostgreSQL

Para facilitar, criei uma instância Docker com a imagem original do PostgreSQLQL. Caso já o tenha instalado em sua máquina, desconsidere.

```commandline
docker pull PostgreSQL

docker run --name teste_datetime -e PostgreSQL_PASSWORD=password -d PostgreSQL

# confirmando existencia
docker container ps
#CONTAINER ID   IMAGE      COMMAND                  CREATED         STATUS         PORTS                    NAMES
#c77150c506a8   PostgreSQL   "docker-entrypoint.s…"   6 seconds ago   Up 5 seconds
```

### Modelo de dados e conexão com SQLAlchemy

Crio, em um arquivo `models.py`, a classe que representará a tabela `datetime` do banco de dados. Nela teremos os campos `date_time_tz_aware`, `date_time_aive` que são, ambos, [`DateTime()`](https://docs.sqlalchemy.org/en/14/core/type_basics.html#sqlalchemy.types.DateTime), com o parâmetro [`*time zone*=True`](https://docs.sqlalchemy.org/en/14/core/type_basics.html#sqlalchemy.types.DateTime.params.*time zone*) **verdadeiro** e **falso**, respectivamente. Os campos `isoformat_tz_aware` e `isoformat_naive` serão os campos textuais que persisitrão os dados de data e hora em formato [`isoformat()`](https://docs.python.org/3/library/datetime.html#datetime.datetime.isoformat).

```python
# models.py
import json

from sqlalchemy import Integer, DateTime, Text
from sqlalchemy import create_engine, Column
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()


BD_USERNAME = "PostgreSQL"
BD_PASSWORD = "password"
BD_HOST = "localhost"
BD_PORT = "5433"
BD_NAME = "PostgreSQL"


def db_connect():
    return create_engine(
        f"PostgreSQLql+psycopg2://{BD_USERNAME}:{BD_PASSWORD}@{BD_HOST}:{BD_PORT}/{BD_NAME}",
        json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False, default=str),
    )


def create_table(engine):
    Base.metadata.create_all(engine)


class DateTimeTable(Base):
    __tablename__ = "datetime"

    id = Column(Integer, primary_key=True)
    date_time_tz_aware = Column(DateTime(*time zone*=True))
    isoformat_tz_aware = Column(Text)
    date_time_naive = Column("datetime_naive", DateTime(*time zone*=False))
    isoformat_naive = Column(Text)


engine = db_connect()
create_table(engine)

```

### Identificando *time zone* das instâncias de trabalho

Para confirmar que estamos reproduzindo as mesmas situações, vamos confirmar o *time zone* da base de dados.

**Docker PostgreSQL**  

```commandline
psql -h localhost -U PostgreSQL -p 5433
show *time zone*;
# *time zone* 
#----------
# Etc/UTC
#(1 row)

```

Ao executar a consulta `select now()`, ele me dá a data e hora com a info de *time zone* utc (+00):

```commandline
select now();
#              now              
#-------------------------------
# 2022-05-27 15:36:59.903336+00
#(1 row)


```

E o mesmo com python:

**python**

```python
from datetime import datetime
datetime.now().as*time zone*().tzinfo
#datetime.*time zone*(datetime.timedelta(days=-1, seconds=75600), '-03')
```

Ou seja, o sistema no qual está rodando o python, está com o *time zone* -03 em relação ao UTC.

> :warning: Atenção, dependendo de como estiver configuado seu sistema, esse resultado poderá estar diferente do meu.

## TL/DR  

* É possível usar tanto o `timedelta` como `TimeZone`, do `pytz` para definir o `tzinfo` de uma instância `datetime`. Contudo, **é preciso cuidado com relação ao método usado na atribuição do `tzinfo`:**
  * Caso se esteja usando uma instância `TimeZone` do `pytz`, é indicado usar o método `localize`;
  
  ```python
  BR_TIME_ZONE = pytz.timezone("America/Sao_Paulo")
  date_time_ibject = datetime(2022, 5, 27, 12, 30, 0, 0)
  BR_TIME_ZONE.localize(date_time_ibject)
  ```

  * Já usando o `timedelta`, pode-se fazê-lo tanto na criação da instância `datetime`, quanto usando o método `replace` do objeto `datetime` já instanciado;
  
  ```python
  BR_TIME_ZONE = timezone(timedelta(hours=-3))
  date_time_object = datetime(2022, 5, 27, 12, 30, 0, 0, tzinfo=BR_TIME_ZONE)
  # OU
  date_time_object = datetime(2022, 5, 27, 12, 30, 0, 0)
  date_time_object.replace(tzinfo=BR_TIME_ZONE)
  ``` 

* Os dados de data e hora são sempre armazenados em UTC no PostgreSQL, independente de estarmos ou não usando campos com *time zone* conscientes. Logo, ao persistir um dado com informação de *time zone*, o mesmo será convertido e persisitido em UTC, mesmo em campos ingênuos. Objetos sem informação de *time zone*, serão persistido como tais por se entender já estarem em UTC. A diferênça em relação a esses tipos da cmpos se dá pelo fato do primeiro armazenar a informação do *time zone* e o último, não.
* A diferença entre campo consciente e ingênuo se dá nas consultas: Os campos consceintes, ao serem cosnutados por uma sessão com determinado *time zone* diferente do padrão (UTC), retornará os dados convertidos ao *time zone* da sessão;
  * Para definir o *time zone* de uma sessão, pode-se usar: 
  ```
  # psql
  set timezone = 'America/Sao_Paulo';
  ```
  ou 
  ```python
  # SQLAlchemy
  engine = create_engine(..., connect_args={"options": "-c timezone=-3"})
  ```
  