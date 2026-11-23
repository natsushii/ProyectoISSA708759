import time
import boto3
from boto3.dynamodb.conditions import Key

REGION = "us-east-1"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
users_table = dynamodb.Table("recing_users")
movies_table = dynamodb.Table("recing_movies")
ratings_table = dynamodb.Table("recing_ratings")

_movies_cache = None


def _scan_all(table, **kwargs):
    """Scan con paginación: DynamoDB devuelve máximo 1 MB por llamada."""
    resp = table.scan(**kwargs)
    items = resp["Items"]
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp["Items"])
    return items


#pelis
def get_all_movies():
    """Catálogo completo (1,682 películas). Se carga una sola vez y se guarda en memoria."""
    global _movies_cache
    if _movies_cache is None:
        movies = _scan_all(movies_table)
        for m in movies:
            m["movie_id"] = int(m["movie_id"])
            m["num_ratings"] = int(m["num_ratings"])
            m["avg_rating"] = float(m["avg_rating"])
        _movies_cache = {m["movie_id"]: m for m in movies}
    return _movies_cache


def get_movie(movie_id):
    return get_all_movies().get(int(movie_id))


def search_movies(text, limit=15):
    text = text.lower().strip()
    found = [m for m in get_all_movies().values() if text in m["title"].lower()]
    return sorted(found, key=lambda m: -m["num_ratings"])[:limit]


def popular_movies(n=10, min_ratings=50, exclude_ids=()):
    """Mejor calificadas con suficientes votos. Se usa para usuarios sin historial."""
    exclude = set(exclude_ids)
    pool = [m for m in get_all_movies().values()
            if m["num_ratings"] >= min_ratings and m["movie_id"] not in exclude]
    pool.sort(key=lambda m: (-m["avg_rating"], -m["num_ratings"]))
    return pool[:n]


#usuarios
def get_user(user_id):
    return users_table.get_item(Key={"user_id": int(user_id)}).get("Item")


def register_user(age, gender, occupation, zip_code="00000"):
    """Crea un usuario nuevo con el siguiente ID disponible y devuelve su ID."""
    ids = _scan_all(users_table, ProjectionExpression="user_id")
    new_id = max(int(i["user_id"]) for i in ids) + 1
    users_table.put_item(Item={
        "user_id": new_id, "age": int(age), "gender": str(gender),
        "occupation": str(occupation), "zip": str(zip_code),
    })
    return new_id


#calificaciones
def rate_movie(user_id, movie_id, rating):
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise ValueError("La calificación debe estar entre 1 y 5")
    if get_user(user_id) is None:
        raise ValueError(f"El usuario {user_id} no existe")
    if get_movie(movie_id) is None:
        raise ValueError(f"La película {movie_id} no existe")
    ratings_table.put_item(Item={
        "user_id": int(user_id), "movie_id": int(movie_id),
        "rating": rating, "timestamp": int(time.time()),
    })


def get_user_ratings(user_id):
    """Historial del usuario con títulos, de lo más reciente a lo más antiguo."""
    kwargs = {"KeyConditionExpression": Key("user_id").eq(int(user_id))}
    resp = ratings_table.query(**kwargs)
    items = resp["Items"]
    while "LastEvaluatedKey" in resp:
        resp = ratings_table.query(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp["Items"])

    movies = get_all_movies()
    history = [{
        "movie_id": int(i["movie_id"]),
        "title": movies.get(int(i["movie_id"]), {}).get("title", "?"),
        "rating": int(i["rating"]),
        "timestamp": int(i["timestamp"]),
    } for i in items]
    return sorted(history, key=lambda h: -h["timestamp"])


def get_seen_movie_ids(user_id):
    return {h["movie_id"] for h in get_user_ratings(user_id)}


if __name__ == "__main__":
    # Prueba rápida (solo lectura, no modifica nada)
    print("Usuario 1:", get_user(1))
    print("Películas en catálogo:", len(get_all_movies()))
    print("Búsqueda 'star wars':", [m["title"] for m in search_movies("star wars")])
    print("Calificaciones del usuario 1:", len(get_user_ratings(1)))
    print("\nPopulares:")
    for m in popular_movies(5):
        print(f"  {m['title']}  ({m['avg_rating']}, {m['num_ratings']} votos)")