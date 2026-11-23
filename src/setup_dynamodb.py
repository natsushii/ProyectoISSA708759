import boto3
import pandas as pd
from decimal import Decimal
from pathlib import Path

REGION = "us-east-1"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "ml-100k"

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def create_table(name, key_schema, attribute_definitions):
    existing = [t.name for t in dynamodb.tables.all()]
    if name in existing:
        print(f"La tabla {name} ya existe")
        return dynamodb.Table(name)
    table = dynamodb.create_table(
        TableName=name,
        KeySchema=key_schema,
        AttributeDefinitions=attribute_definitions,
        BillingMode="PAY_PER_REQUEST",  # sin costo fijo, pagas por uso
    )
    table.wait_until_exists()
    print(f"Tabla {name} creada")
    return table


users_table = create_table(
    "recing_users",
    [{"AttributeName": "user_id", "KeyType": "HASH"}],
    [{"AttributeName": "user_id", "AttributeType": "N"}],
)
movies_table = create_table(
    "recing_movies",
    [{"AttributeName": "movie_id", "KeyType": "HASH"}],
    [{"AttributeName": "movie_id", "AttributeType": "N"}],
)
ratings_table = create_table(
    "recing_ratings",
    [
        {"AttributeName": "user_id", "KeyType": "HASH"},
        {"AttributeName": "movie_id", "KeyType": "RANGE"},
    ],
    [
        {"AttributeName": "user_id", "AttributeType": "N"},
        {"AttributeName": "movie_id", "AttributeType": "N"},
    ],
)

# ---- Cargar datos ----
ratings = pd.read_csv(DATA_DIR / "u.data", sep="\t",
                      names=["user_id", "movie_id", "rating", "timestamp"])
movies = pd.read_csv(DATA_DIR / "u.item", sep="|", encoding="latin-1", header=None,
                     usecols=[0, 1, 2], names=["movie_id", "title", "release_date"])
users = pd.read_csv(DATA_DIR / "u.user", sep="|",
                    names=["user_id", "age", "gender", "occupation", "zip"])

# Popularidad por película (sirve después para usuarios nuevos sin historial)
stats = ratings.groupby("movie_id").rating.agg(["count", "mean"])
movies = movies.merge(stats, left_on="movie_id", right_index=True, how="left").fillna(0)

print("Cargando usuarios...")
with users_table.batch_writer() as batch:
    for r in users.itertuples():
        batch.put_item(Item={
            "user_id": int(r.user_id), "age": int(r.age), "gender": str(r.gender),
            "occupation": str(r.occupation), "zip": str(r.zip),
        })

print("Cargando películas...")
with movies_table.batch_writer() as batch:
    for r in movies.itertuples():
        batch.put_item(Item={
            "movie_id": int(r.movie_id), "title": str(r.title),
            "release_date": str(r.release_date) if r.release_date else "",
            "num_ratings": int(r.count),
            "avg_rating": Decimal(str(round(float(r.mean), 2))),
        })

print("Cargando calificaciones (tarda unos minutos)...")
with ratings_table.batch_writer() as batch:
    for r in ratings.itertuples():
        batch.put_item(Item={
            "user_id": int(r.user_id), "movie_id": int(r.movie_id),
            "rating": int(r.rating), "timestamp": int(r.timestamp),
        })

print("Listo.")