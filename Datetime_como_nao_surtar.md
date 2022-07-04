# Entendendo a fundo a relação datetime com e sem *time zone* entre SQLAlchemy e PostgreSQL

Há algum tempo comecei a perceber um "comportamento estranho" relacionado aos dados de data e hora num sistema que estava desenvolvendo. Minha reação inicial, praticamente um instinto de sobrevivencia, foi de simplemente resolver a situação contornando o problema. Mas chegou um momento que precisei entender a origem do mesmo. Mais uma vez tive que fazer um exercício de seguir/isolar o problema que me assombrava ([veja outros artigos que produzi sobre bugs/comportamentos estranhos que observo]()), tentando isolá-lo e compreender o motivo da sua existencia. Esse processo tomou-me alguns dias e, claro, proporcionou alguns aprendizados. 

Ainda que agora, tendo resolvido e entendido o "comportamento estranho", tudo parece óbvio, decidi compartilhar um pouco deste processo, pois no processo de busca por soluções não encontrei nada que me ajudasse de forma objetiva.

Criei um ambiente para reproduzir esses "comportamentos estranhos" ( [há uma sessão sobre como preparar um ambiente para poder reproduzir esses códigos](#Preparando-ambiente-de-desenvolvimento) ) e deixarei os trechos de códigos usados, para que vocês possam reproduzir os passos dados. Irei trabalhar em todos os exemplos com um mesmo objeto de data e hora (instância `DateTime`) mudando, apenas o uso de *time zone*, para torná-los conscientes ou não (leia um pouco sobre isso [aqui](https://docs.python.org/3/library/datetime.html#aware-and-naive-objects)).

## Contextualizando o sistema

Antes de tudo, lhes resumo a parte que importa do sistema:  

O mesmo estava numa instância EC2 da AWS, com *time zone* UTC, e nele eu manipulava um dado de data e hora, usando o módulo python [`datetime`][], com *time zone* consciente (`aware`), transformando-os ao *time zone* do Brasil (-03). Esse dado era, então, persistido no banco de dados [PostgreSQL][], que estava numa instância da azure, também com *time zone* UTC. Os dados eram persistidos em duas colunas diferentes: uma coluna [DateTime com *time zone* consciente](https://www.PostgreSQLql.org/docs/current/datatype-datetime.html) e numa coluna de texto onde, além da data e hora em formato [iso](https://docs.python.org/3/library/datetime.html#datetime.date.isoformat), uma observação textual era adicionada (que não vem ao caso, agora). Mas é importante saber que tínhamos o mesmo dado de data e hora persistido como tal e como texto.  

Um detalhe não menos importante é o fato de eu estar usando o módulo [`pytz`](https://pythonhosted.org/pytz/) para definir o *time zone* do Brasil (`America/Sao_Paulo`).

O [SQLAlchemy](https://www.sqlalchemy.org/) estava sendo usado para fazer a conexão com o banco de dados, commit e etc. E, pensando em facilitar a minha vida estive usando o [DBeaver](https://dbeaver.io/), uma interface gráfica para gestão de banco de dados. Ou seja, usava o DBeaver para conectar ao banco de dados e observar o que estava sendo persistido sem precisar fazê-lo pelo [`psql`](https://www.postgresql.org/docs/current/app-psql.html).

## Reproduzindo comportamento estranho I

Basicamente criei uma instância `datetime` ingenua (*naive*) em relação ao *time zone* e outra com *time zone* declarado ( consciente, *aware*). Criei uma instância da tabela persistindo esses dados, mantendo o objeto com *time zone* consciente, na coluna consciente e o ingenuo na coluna ingenua. O mesmo para os campos `isofromat`.

```python
import pytz
from datetime import datetime
from sqlalchemy.orm import sessionmaker


engine = db_connect()
Session = sessionmaker(bind=engine)
session = Session()


BR_TIME_ZONE = pytz.*time zone*("America/Sao_Paulo")

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

Ao fazer o commit e consultar a base de dados, começa o terror e pânico:

Ao usar o DBeaver para acessar o registro criado (seja pela interface gráfica como pela query da GUI), observei que:

* O dado persistido na coluna consciente, o valor foi alterado em seis minutos (acrescidos). **Deveria ser 12:30 e passou a ser 12:36**, ao passo que a informação de *time zone* e apresentada de forma correta: -0300;  
* O dado da coluna `iso_format_tz_aware` possui a informaçao sem qualquer alteraçao. Ao passo que a *time zone* informada não é a esperada (-3 horas). É -03 horas e 06 minutos. Lembrem-se que o *time zone* da coluna `date_time_aware` é informado apenas `-0300`;
* Os dados persistidos nos campos *time zone* ingenuos não apresentaram qualquer alteraçao.

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
| 1 | 2022-05-27 12:36:00.000 -0300 | 2022-05-27T12:30:00-03:06 | 2022-05-27 12:30:00.000 | 2022-05-27T12:30:00 |

Ao acessar esses dados usando o SQLAlchemy, a bagunça aumenta:

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |  |
|-------------|---|---|---|---|---|
| 1| 2022-05-27 15:36:00+00:00 | 2022-05-27T12:30:00-03:06 | 2022-05-27 12:30:00 | 2022-05-27T12:30:00 |

Reparem que, acessando os dados pelo SQLAlchemy, temos:  

* Na coluna `date_time_tz_aware`, o objeto tem três horas e seis minutos acrescidos e o *time zone* informado como UTC (+00:00).  
* Os dados das colunas `iso_format`, `date_time_naive` e `isoformat_naive` apresentam os dados assim como estão no banco de dados.

Comportamentos estanhos a serem resolvidos:
* O *time zone* deveria ser de -0300 hora. de onde veio os seis munitos a mais?;
* Afinal, o dado é persistido no banco de dados em UTC ou no *time zone* persistido?

### Resolvendo problema de definição de *time zone* I

Ao conversar com um colega, me foi informado que a forma como eu estava definido o *time zone* esatava equivocado. A única direção dada, por ele foi [essa pergunta no SOF](https://stackoverflow.com/questions/1379740/pytz-localize-vs-datetime-replace).
Os detalhes são um pouco confusos, mas um comentário me chamou a atençao:

> @MichaelWaterfall: pytz.*time zone*() may correspond to several tzinfo objects (same place, different UTC offsets, *time zone* abbreviations). tz.localize(d) tries to find the correct tzinfo for the given d local time (some local time is ambiguous or doesn't exist). replace() just sets whatever (random) info pytz *time zone* provides by default without regard for the given date (LMT in recent versions). tz.normalize() may adjust the time if d is a non-existent local time e.g., the time during DST transition in Spring (northern hemisphere) otherwise it does nothing in this case.

Em trdução livre:
> pytz.*time zone*() pode corresponder a objetos com diferentes tzinfo (mesmo local, diferentes *offset* em relaçõ ao UTC). tz.localize(d) tenta encontrar o tzinfo correto para um dada hora local (algumas horas locais são ambiguas ou inexistentes). replace() apenas define qualquer informação de *time zone* por padrão sem se preocupar com a data. tz.normalize() deve ajustar a informação de tempo se o objeto  d não possuir informação de hora local.

Então, como estou usando o `pytz` para definir um objeto de *time zone*, o `replace` não seria a forma correta, mas sim, o método `localize` do pórprio *time zone*. Reparem a diferença que isso fez no parametro `tzinfo` da instância:

```
BR_TIME_ZONE = pytz.*time zone*("America/Sao_Paulo")
naive = datetime(2022, 5, 27, 12, 30, 0, 0)
naive.replace(tzinfo=BR_TIME_ZONE)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=<DstTzInfo 'America/Sao_Paulo' LMT-1 day, 20:54:00 STD>)
BR_TIME_ZONE.localize(naive)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=<DstTzInfo 'America/Sao_Paulo' -03-1 day, 21:00:00 STD>)
```

Reparem que há uma diferença de seis minutos entre os objetos resultantes.

Fiz mais um teste para entender se o problema é o método `replace` ou a forma como o `pytz` define o *time zone*:

```python
datetime(2022, 5, 27, 12, 30, 0, 0, tzinfo=BR_TIME_ZONE)
# datetime.datetime(2022, 5, 27, 12, 30, tzinfo=<DstTzInfo 'America/Sao_Paulo' LMT-1 day, 20:54:00 STD>)
```

Mesmo passando o *time zone* do `pytz` como parâmetro `tzinfo`, a diferença de seis minutos segue (20:54). Ou seja, também não seria a forma correta.

Ao salvar no banco de dados o objeto `aware` criado usando o `localize`, os dados foram, enfim, salvos de forma correta:

| date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive | isofomat_naive |
|---|---|---|---|---|
| 2022-05-27 12:30:00.000 -0300 | 2022-05-27T12:30:00-03:00 | 2022-05-27 12:30:00.000 | 2022-05-27T12:30:00 | 2022-05-27T12:30:00 |

OK, um problema resolvido. Mas ainda fica o misterio das conversões entre o dado acessado pelo DBeaver daquele acessado pelo SQLAlchemy.

### Resolvendo problema de definição de *time zone* II

Uma semana depois de solucionado esse primeiro problema na definição do *time zone*, o [@dunossauro](https://twitter.com/dunossauro) fez uma [ live de python sobre `datetime`](https://youtu.be/BImF-dZYass?t=3948). Fui assistir e vi que, ele indicou a definição de *time zone* usando [`timedelta`](https://docs.python.org/3/library/datetime.html#timedelta-objects).

Vamos testar, então: 

```python
from datetime import *time zone*, timedelta

# BR_TIME_ZONE = pytz.*time zone*("America/Sao_Paulo")
BR_TIME_ZONE = *time zone*(timedelta(hours=-3))
```

O processo de definição do *time zone*, seguiu o mesmo, usando o [`localize`]().

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
|  | 2022-05-27 12:30:00.000 -0300 | 2022-05-27T12:30:00-03:00 | 2022-05-27 12:30:00.000 | 2022-05-27T12:30:00 |

Bom, parece que essa forma também persiste os dados de forma correta e, ainda nos poupa de usar um módulo (o `pytz`). Gracias, [@dunossauro](https://twitter.com/dunossauro)!

## Reproduzindo comportament0 estranho II

Ainda que me tenha tomado um tempo considerável, a solução anterior não chegou a esgotar a minha paciência. Por isso, ao invés de ser objetivo com o pblema que ainda tenha que resolver, fiz mais alguns testes, para tentar entender, de vez, a diferneça entre uma coluna com *time zone* consciente e nao consciente no PostgreSQLQL.

#### Primeiro teste:

Inseri em ambos campos de `DateTime` (consciente e ingênuo), um objeto com *time zone* consciente:

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

Acessando esse dado pelo DBeaver, tenho:

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
| 2 | 2022-05-27 12:30:00.000 -0300 | 2022-05-27T12:30:00-03:00 | 2022-05-27 15:30:00.000 | 2022-05-27T12:30:00-03:00 |

Reparem que:

* Nas colunas `tz_aware` nada mudou do exemplo anterior, exceto pelo fato de eu ja ter corrigido aquela diferença de seis minutos que tinhamos antes.
* Na coluna `naive`, passo a ter o objeto alterado, sendo acrescido 3 horas;

Ao acessar tais dados pelo SQLAlchemy, a informação persistida no campo *time zone* consciente é retornada acrescida de trẽs horas e no campo ingenuo, não há alteração.

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
| 2 | 2022-05-27 15:30:00+00:00 | 2022-05-27T12:30:00-03:00 | 2022-05-27 15:30:00 | 2022-05-27T12:30:00-03:00 |

#### Segundo teste:

Inseri em ambos campos de `DateTime`, o objeto com *time zone* ingênuo, sem info de *time zone*.

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

Acessando esse registro pelo DBeaver, tenho:

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
| 2 | 2022-05-27 09:30:00.000 -0300 | 2022-05-27T12:30:00 | 2022-05-27 12:30:00.000 | 2022-05-27T12:30:00 |

Percebam que:

- Na coluna `tz_aware` o campo de hora possui tres horas descontada, e a info de *time zone* é de -0300.
- Na coluna `naive`, os objetos possuem os valores respeitados;

Acessando so dados pelo SQLAlchemy, passo a ter:

| id | date_time_tz_aware | iso_format_tz_aware | date_time_naive | isofomat_naive |
|---|---|---|---|---|
| 2 | 2022-05-27 12:30:00+00:00 | 2022-05-27T12:30:00 | 2022-05-27 12:30:00 | 2022-05-27T12:30:00 |

- Na coluna `tz_aware`, a hora conforme salvo no banco, mas com info de *time zone* para utc (+00:00:00)
- Na coluna `naive` também, mas, como esperado sem a info de *time zone*;

Com esses testes fiquei ainda mais perdido: eu só queria entender a diferença no comportamento dos campo do PostgreSQLQL com *time zone* consciente ingênuo, mas acabei mais confuso ainda, pela diferença entre o resgatado pelo banco com DBeaver e SQLAlchemy.

**Ficaram duas perguntas norteadoras:**

* O PostgreSQLql, em um campo *time zone* aware, armazena a informação como persistida (ou seja, cada registro com um *time zone* diferente) ou ele converte, homogeneizando todos os dados para um determinado *time zone*?
* Vi que o SQLAlchemy por padrão retorna os dados em UTC, mesmo. A pergunta que me fiz foi: Por que? Ou melhor:
* É o SQLAlchemy que converte os dados para UTC?


### Resolvendo dúvida sobre dados persistidos

Segui "encucado" com o fato de ter informações diferentes sobre os registros persistidos no banco de dados de acoro com a ferramenta usada (nos casos anteriores, DBeaver - apresentando os dados em +0300 - e SQLAlchemy - apresentadno os dados em +0000).

Decidi acessar o banco e fazer as consultas apresentadas anteriormente pelo [psql](https://www.PostgreSQLql.org/docs/current/app-psql.html) e confirmar o *time zone*, assim como já o tinha feito na [Preparação do ambiente de desenvolvimento](#Preparando-ambiente-de-desenvolvimento). A diferença foi que fiz o mesmo no DBeaver também.

![](img/show_*time zone*_psql.png)
![](img/show_*time zone*_dbeaver.png)

Eis, então, que fica evidente: o mesmo banco de dados apresentando `*time zone*s` diferentes de acordo com a ferramenta usada. Entendo que o DBeaver, por se tratar de uma interface gráfica desenhada para facilitar a vida dos usuário e gestores de banco de dados, identifica o *time zone* da máquina onde o mesmo está instalada e define o *time zone* de acordo com isso para que os dados sejam retornados conforme dito *time zone*.

Isso me fez lembrar da documentação do PostgreSQL que já havia lido, mas não tinha dado muita atenção:

> For timestamp with time zone, the internally stored value is always in UTC (Universal Coordinated Time, traditionally known as Greenwich Mean Time, GMT). An input value that has an explicit time zone specified is converted to UTC using the appropriate offset for that time zone. If no time zone is stated in the input string, then it is assumed to be in the time zone indicated by the system's *time zone* parameter, and is converted to UTC using the offset for the *time zone* zone.
> [fonte](https://www.PostgreSQLql.org/docs/current/datatype-datetime.html)

Em traduçao livre:
> Para dados com informaçao de time zone, o valor armazenado estara sempre em UTC (Universal Coordinated Time, traditionally known as Greenwich Mean Time, GMT). Um valor de entrada que nao tenha time zone declarado explicitamente sera convertido a UTC usando o time zone indicado pelo sistema.

A partir disso, várias constatações:
* Os dados que possuem a informação de *time zone*, são convertidos a UTC. Os dado naive enviado é entendido como já estando em UTC, logo não é convertido.
* O DBeaver identificou o *time zone* da minha máquina e apresentava todos os dados considerando tal informação.
* Não é o SQLAlchemy que define como os dados serão resgatados, mas o PostgreSQL. Na verdade, essa definição é feita pela sessão de conexão com o banco de dados. Vejam:

```python
psql -h localhost -U PostgreSQL -p 5432 PostgreSQL

PostgreSQL= show *time zone*;
#  *time zone* 
# ----------
#  Etc/UTC
# (1 row)
select * from datetime;
```

Com uma session recém iniciada, o *time zone* é configurado para UTC.
Ao fazer um select, a coluna com *time zone* consciente (`date_time_tz_aware`), apresenta os dados como são salvos no banco, em UTC.

Se, na mesma conexão, eu configuro o *time zone* para `America/Sao_Paulo`, e eecuto a mesma query, os dados na coluna com *time zone* consciente serão apresentados convertidos ao *time zone* definido na conexão.

```python
PostgreSQL=# set *time zone* = 'America/Sao_Paulo';
#SET
PostgreSQL=# show *time zone*;
#      *time zone*      
# -------------------
#  America/Sao_Paulo
# (1 row)


select * from datetime;
```

Tudo parece bem obvio, não? Mas uma ciosa que foi fundamental para a minha confusão mental sobre esse comportamente estranho é que eu estive usando o DBeaver como interface gráfica para ver como os dados estavam armazenados no banco de dados. E o DBeaver em algum momento, identifica o *time zone* do sistema que o está executando e o usa na configuração da sessão. Então, eu acessava os dados pelo SQLAlchemy, que usa uma sessão padrão, sem configuração de *time zone*, logo *time zone* UTC, e recebia os dados como tal. Mas ao olhar os mesmos dados pelo DBeaver, os via convertidos para a *time zone* do meu sistema, `America/Sao_Paulo`, e os via convertido, com outros valores na coluna com *time zone* consciente; Com isso, eu desenvolvi um sistema, entendendo que os dados estariam em -3, pois foram manipulados e salvos no banco de dados assim, e assim os via pelo DBeaver, mas ao consultar o banco de dados pelo SQLAlchemy os mesmos vinham em UTC. Logo, eu tinha problemas no desencadeamento do sistema pois a data e hora retorndos da consulta eram usados para filtrar outros dados que tinham a data e hora (*time zone* -3) armazenados em um campo de texto (logo esses não passavam por qualquer processo de conversão).  

Enfim, vivendo e aprendendo.

E como fariamos para definir o *time zone* de uma session usando o SQLAlchemy?
`engine = create_engine(..., connect_args={"options": "-c *time zone*=utc"})`

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

## Identificando *time zone* das instâncias de trabalho

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

Ao trabalhar com objetos datetime, salva-los num banco de dados PostgreSQL, em campo DateTime, e resgata-los com SQLAlchemy, pude perceber que algumas conversoes estavam sendo feitas. Fiquei perdido sem entender em que momento essas conversões acontecem nem como controla-las. ~~Afinal, a pergunta e:~~  

Como evitar ao máximo as conversões entre o objeto `datetime`, o que está salvo no banco de dados e o que é resgatado pelo SQLAlchemy?
