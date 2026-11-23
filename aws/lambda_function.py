import json
import os
import boto3
from boto3.dynamodb.conditions import Key

REGION = os.environ.get("AWS_REGION", "us-east-1")
ENDPOINT_NAME = os.environ.get("ENDPOINT_NAME", "recing-fm-endpoint")

# Deben coincidir con los usados al entrenar el modelo
N_USERS = 943
N_MOVIES = 1682
FEATURE_DIM = N_USERS + N_MOVIES

dynamodb = boto3.resource("dynamodb", region_name=REGION)
ratings_table = dynamodb.Table("recing_ratings")
movies_table = dynamodb.Table("recing_movies")
runtime = boto3.client("sagemaker-runtime", region_name=REGION)

_movies = None  # se conserva entre invocaciones "calientes"


def get_movies():
    global _movies
    if _movies is None:
        resp = movies_table.scan()
        items = resp["Items"]
        while "LastEvaluatedKey" in resp:
            resp = movies_table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp["Items"])
        _movies = {
            int(m["movie_id"]): {
                "movie_id": int(m["movie_id"]),
                "title": m["title"],
                "num_ratings": int(m["num_ratings"]),
                "avg_rating": float(m["avg_rating"]),
            }
            for m in items
        }
    return _movies


def get_seen_ids(user_id):
    kwargs = {
        "KeyConditionExpression": Key("user_id").eq(user_id),
        "ProjectionExpression": "movie_id",
    }
    resp = ratings_table.query(**kwargs)
    items = resp["Items"]
    while "LastEvaluatedKey" in resp:
        resp = ratings_table.query(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp["Items"])
    return {int(i["movie_id"]) for i in items}


def popular(movies, seen, n, min_ratings=50):
    pool = [m for m in movies.values()
            if m["num_ratings"] >= min_ratings and m["movie_id"] not in seen]
    pool.sort(key=lambda m: (-m["avg_rating"], -m["num_ratings"]))
    return [{"movie_id": m["movie_id"], "title": m["title"], "score": m["avg_rating"]}
            for m in pool[:n]]


def predict_scores(user_id, movie_ids, batch_size=500):
    scores = []
    for s in range(0, len(movie_ids), batch_size):
        chunk = movie_ids[s:s + batch_size]
        instances = [
            {"data": {"features": {"keys": [user_id - 1, N_USERS + m - 1],
                                   "values": [1, 1],
                                   "shape": [FEATURE_DIM]}}}
            for m in chunk
        ]
        resp = runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType="application/json",
            Body=json.dumps({"instances": instances}),
        )
        out = json.loads(resp["Body"].read())
        scores.extend(float(p["score"]) for p in out["predictions"])
    return [min(5.0, max(1.0, s)) for s in scores]


def lambda_handler(event, context):
    if isinstance(event.get("body"), str):  # por si se invoca vía URL/API Gateway
        event = json.loads(event["body"])

    try:
        user_id = int(event["user_id"])
    except (KeyError, ValueError, TypeError):
        return {"error": "Falta 'user_id' o no es un número"}
    top_n = max(1, min(int(event.get("top_n", 10)), 50))

    movies = get_movies()
    seen = get_seen_ids(user_id)

    # Usuarios que el modelo no conoce (nuevos): películas populares
    if user_id < 1 or user_id > N_USERS:
        return {"user_id": user_id, "mode": "popular",
                "recommendations": popular(movies, seen, top_n)}

    candidates = [m for m in movies if m not in seen]
    try:
        scores = predict_scores(user_id, candidates)
    except Exception as e:
        print("Error al invocar SageMaker:", repr(e))
        return {"user_id": user_id, "mode": "popular_fallback",
                "warning": "No se pudo consultar el modelo: " + str(e)[:200],
                "recommendations": popular(movies, seen, top_n)}

    ranked = sorted(zip(candidates, scores), key=lambda x: -x[1])[:top_n]
    return {
        "user_id": user_id,
        "mode": "personalized",
        "recommendations": [
            {"movie_id": m, "title": movies[m]["title"], "score": round(s, 3)}
            for m, s in ranked
        ],
    }