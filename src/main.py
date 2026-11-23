import json
import boto3
import database as db

REGION = "us-east-1"
LAMBDA_NAME = "recing-recommend"
lambda_client = boto3.client("lambda", region_name=REGION)

current_user = None


def ask_int(prompt, low=None, high=None):
    while True:
        text = input(prompt).strip()
        try:
            value = int(text)
        except ValueError:
            print("  Escribe un número entero.")
            continue
        if (low is not None and value < low) or (high is not None and value > high):
            print(f"  El valor debe estar entre {low} y {high}.")
            continue
        return value


def require_login():
    if current_user is None:
        print("  Primero inicia sesión o registra un usuario (opciones 1 o 2).")
        return False
    return True


def register():
    global current_user
    print("\n--- Registrar usuario ---")
    age = ask_int("Edad: ", 5, 120)
    gender = ""
    while gender not in ("M", "F"):
        gender = input("Género (M/F): ").strip().upper()
    occupation = input("Ocupación: ").strip() or "other"
    user_id = db.register_user(age, gender, occupation)
    current_user = user_id
    print(f"  Usuario creado. Tu ID es {user_id} (sesión iniciada).")


def login():
    global current_user
    print("\n--- Iniciar sesión ---")
    user_id = ask_int("ID de usuario: ", 1)
    if db.get_user(user_id) is None:
        print("  Ese usuario no existe.")
        return
    current_user = user_id
    print(f"  Sesión iniciada como usuario {user_id}.")


def search():
    print("\n--- Buscar películas ---")
    text = input("Título (o parte del título): ").strip()
    if not text:
        return
    results = db.search_movies(text)
    if not results:
        print("  Sin resultados.")
    for m in results:
        print(f"  [{m['movie_id']:>4}] {m['title']}  (promedio {m['avg_rating']})")


def pick_movie():
    text = input("ID de la película (o escribe parte del título para buscar): ").strip()
    if text.isdigit():
        return int(text)
    results = db.search_movies(text, limit=10)
    if not results:
        print("  Sin resultados.")
        return None
    for m in results:
        print(f"  [{m['movie_id']:>4}] {m['title']}")
    return ask_int("ID de la película: ", 1)


def rate():
    if not require_login():
        return
    print("\n--- Calificar película ---")
    movie_id = pick_movie()
    if movie_id is None:
        return
    movie = db.get_movie(movie_id)
    if movie is None:
        print("  Esa película no existe.")
        return
    print(f"  {movie['title']}")
    rating = ask_int("Calificación (1-5): ", 1, 5)
    db.rate_movie(current_user, movie_id, rating)
    print("  Calificación guardada.")


def my_ratings():
    if not require_login():
        return
    history = db.get_user_ratings(current_user)
    print(f"\n--- Películas calificadas por el usuario {current_user} ({len(history)}) ---")
    for h in history[:30]:
        print(f"  {h['rating']}★  {h['title']}")
    if len(history) > 30:
        print(f"  ... y {len(history) - 30} más")


def recommend():
    if not require_login():
        return
    top_n = ask_int("¿Cuántas recomendaciones quieres? (1-20): ", 1, 20)
    print("  Consultando recomendaciones...")
    resp = lambda_client.invoke(
        FunctionName=LAMBDA_NAME,
        Payload=json.dumps({"user_id": current_user, "top_n": top_n}),
    )
    result = json.loads(resp["Payload"].read())

    if "FunctionError" in resp or "errorMessage" in result:
        print("  Error en Lambda:", result.get("errorMessage", result))
        return
    if "error" in result:
        print("  Error:", result["error"])
        return

    mode = result.get("mode")
    if mode == "personalized":
        print(f"\n--- Recomendaciones personalizadas para el usuario {current_user} ---")
    elif mode == "popular":
        print("\n--- Aún no hay modelo para tu usuario: estas son las más populares ---")
    else:
        print("\n--- No se pudo consultar el modelo: se muestran las más populares ---")
        print("  Aviso:", result.get("warning", ""))

    for i, r in enumerate(result["recommendations"], 1):
        print(f"  {i:>2}. {r['title']}  (puntuación {r['score']})")


MENU = """
===== Rec'ing Movies AI =====
 1. Registrar usuario
 2. Iniciar sesión
 3. Buscar películas
 4. Calificar una película
 5. Ver mis calificaciones
 6. Obtener recomendaciones
 0. Salir
"""

ACTIONS = {"1": register, "2": login, "3": search,
           "4": rate, "5": my_ratings, "6": recommend}


def main():
    print("Cargando catálogo...")
    db.get_all_movies()
    while True:
        print(MENU)
        if current_user is not None:
            print(f"Usuario actual: {current_user}")
        option = input("Elige una opción: ").strip()
        if option == "0":
            print("¡Hasta luego!")
            break
        action = ACTIONS.get(option)
        if action is None:
            print("  Opción no válida.")
            continue
        try:
            action()
        except Exception as e:
            print("  Ocurrió un error:", e)


if __name__ == "__main__":
    main()