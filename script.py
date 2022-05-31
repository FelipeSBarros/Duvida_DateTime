import pytz

import json
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Integer, DateTime, Text
from sqlalchemy import create_engine, Column
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()

BR_TIME_ZONE = pytz.timezone("America/Sao_Paulo")
BRU_TIME_ZONE = pytz.timezone("Asia/Brunei")
# BR_TIME_ZONE = timezone(timedelta(hours=-3))

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

Session = sessionmaker(bind=engine)
session = Session()

# naive = datetime.now()
naive = datetime(2022, 5, 27, 12, 30, 0, 0)
# aware = naive.replace(tzinfo=BR_TIME_ZONE)
# aware = datetime(2022, 5, 27, 12, 30, 0, 0, tzinfo=BR_TIME_ZONE)
aware = BR_TIME_ZONE.localize(naive)
aware = BRU_TIME_ZONE.localize(naive)

record = DateTimeTable(
    date_time_tz_aware=aware,
    isoformat_tz_aware=f"{aware.isoformat()}",
    date_time_naive=naive,
    isoformat_naive=f"{naive.isoformat()}",
)

session.add(record)
session.commit()
session.close()

session = Session()
for row in session.query(DateTimeTable).all():
    print(
        row.date_time_tz_aware,
        row.isoformat_tz_aware,
        row.date_time_naive,
        row.isoformat_naive,
    )
# id  date_time_tz_aware    iso_format_tz_aware    date_time_naive    isofomat_naive
# 2022-05-27 15:36:00+00:00 2022-05-27T12:30:00-03:06 2022-05-27 12:30:00 2022-05-27T12:30:00

# segundo registro inserindo datetime aware sempre
record2 = DateTimeTable(
    date_time_tz_aware=aware,
    isoformat_tz_aware=f"{aware.isoformat()}",
    date_time_naive=aware,
    isoformat_naive=f"{aware.isoformat()}",
)
session.add(record2)
session.commit()

# terceiro registro inserindo datetime naive sempre
record3 = DateTimeTable(
    date_time_tz_aware=naive,
    isoformat_tz_aware=f"{naive.isoformat()}",
    date_time_naive=naive,
    isoformat_naive=f"{naive.isoformat()}",
)
session.add(record3)
session.commit()

session.close()
