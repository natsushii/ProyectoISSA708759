# Rec'ing Movies AI

Sistema inteligente de recomendación de películas que integra servicios de AWS con aprendizaje automático. Proyecto final de *Integración de Servicios de Aprendizaje Automático* (ITESO).

El usuario interactúa desde una **interfaz de línea de comandos (CLI) en Python**: registra usuarios, califica películas y solicita recomendaciones personalizadas generadas por un modelo de **Factorization Machines** desplegado en **Amazon SageMaker**.

---

## Arquitectura

```
Terminal (CLI)  →  Boto3  →  AWS Lambda  →  DynamoDB   (historial del usuario)
                                  │
                                  └──────→  SageMaker  (predicción de calificaciones)
                                  │
Terminal (CLI)  ←─────────────────┘   (top N de películas no vistas)

S3: dataset procesado y artefactos del modelo · IAM: permisos · CloudWatch: logs de Lambda
```

| Componente | Responsabilidad |
|---|---|
| CLI en Python (`src/main.py`) | Menú para registrar usuarios, buscar y calificar películas y pedir recomendaciones. |
| Boto3 | Comunica el programa local con DynamoDB y con la función Lambda. |
| AWS Lambda (`recing-recommend`) | Lee el historial, genera candidatas no vistas, consulta el modelo y devuelve el top N. |
| Amazon DynamoDB | Almacena usuarios, catálogo de películas y calificaciones. |
| Amazon SageMaker | Entrena y ejecuta el modelo de Factorization Machines. |
| Amazon S3 | Guarda los datos procesados y los artefactos del modelo. |
| AWS IAM | Roles y permisos mínimos para cada servicio. |
| Amazon CloudWatch | Registro de ejecuciones y errores de Lambda. |

### Flujo de una recomendación

1. El usuario elige "Obtener recomendaciones" en la CLI.
2. Python invoca la función Lambda con Boto3 (`user_id`, `top_n`).
3. Lambda consulta en DynamoDB las películas que el usuario ya calificó.
4. Lambda pide al endpoint de SageMaker la calificación esperada de cada película no vista.
5. Lambda ordena de mayor a menor y devuelve el top N.
6. La CLI muestra la lista en la terminal.

### Comportamiento según el usuario

- **Usuarios 1 a 943** (los del dataset): recomendaciones **personalizadas** con el modelo (`mode: personalized`).
- **Usuarios nuevos** (ID 944 en adelante): el modelo aún no los conoce, así que reciben las películas más populares (`mode: popular`). Sus calificaciones quedan guardadas en DynamoDB para incorporarse en un reentrenamiento futuro.
- **Si el endpoint no está disponible**, la Lambda no falla: devuelve películas populares con un aviso (`mode: popular_fallback`).
- Las películas que el usuario ya calificó **siempre se excluyen** de las recomendaciones.

---

## Dataset y modelo

- **Dataset:** [MovieLens 100K](https://grouplens.org/datasets/movielens/100k/) (100,000 calificaciones, 943 usuarios, 1,682 películas, ~94% de sparsity).
- **Algoritmo:** Factorization Machines (SageMaker) en modo regresión. Cada calificación se codifica como un vector disperso *one-hot* (usuario + película) y el modelo predice la calificación.
- **Baseline local:** factorización de matrices con sesgos (SGD en NumPy) para comparar la métrica.
- **Evaluación:** split 80/20 (`random_state=42`) con RMSE y MAE sobre datos de prueba.

| Modelo | RMSE | MAE |
|---|---|---|
| Baseline local (MF con sesgos) | _completar_ | _completar_ |
| Factorization Machines (SageMaker) | _completar_ | _completar_ |

---

## Estructura del repositorio

```
.
├── data/
│   └── README.md               # Instrucciones para obtener el dataset (los datos no se suben)
├── notebooks/
│   └── entrenamiento.ipynb     # Exploración, baseline, entrenamiento y evaluación
├── src/
│   ├── main.py                 # CLI (menú de la terminal)
│   ├── database.py             # Operaciones con DynamoDB (Boto3)
│   ├── setup_dynamodb.py       # Crea las tablas y carga MovieLens
│   ├── endpoint.py             # Despliega / borra / consulta el endpoint de SageMaker
│   └── test_lambda.py          # Prueba la Lambda desde Python
├── aws/
│   └── lambda_function.py      # Código de la función Lambda
├── requirements.txt
└── README.md
```

---

## Requisitos

- Python 3.10 a 3.12 (el SDK de SageMaker v2 puede fallar en versiones más nuevas).
- Una cuenta de AWS y AWS CLI v2.
- Git.

## Instalación

```bash
git clone https://github.com/natsushii/ProyectoISSA708759.git
cd ProyectoISSA708759

python -m venv venv
# Windows (PowerShell):  venv\Scripts\Activate.ps1
# Mac / Linux:           source venv/bin/activate

pip install -r requirements.txt
```

> Si el repositorio está dentro de OneDrive, conviene crear el entorno virtual fuera de la carpeta sincronizada, por ejemplo `python -m venv C:\venvs\recing`.

## Configuración de AWS

Todo el proyecto usa **una sola región: `us-east-1` (N. Virginia)**.

1. **Usuario IAM** (no uses la cuenta root): crea un usuario con acceso programático, genera una *access key* y corre `aws configure` (región `us-east-1`, formato `json`). Verifica con `aws sts get-caller-identity`.
2. **Alerta de presupuesto** en AWS Budgets (por ejemplo 20 USD al mes).
3. **Bucket de S3** privado con un nombre único, por ejemplo `recing-movies-<tu-nombre>`.
4. **Rol de ejecución de SageMaker** con las políticas `AmazonSageMakerFullAccess` y `AmazonS3FullAccess`. Copia su ARN y colócalo en la variable `ROLE_ARN` del notebook y de `src/endpoint.py`.
5. **Tablas de DynamoDB** (se crean con el script):
   ```bash
   python src/setup_dynamodb.py
   ```
   Crea `recing_users`, `recing_movies` y `recing_ratings` (modo *on-demand*) y carga los datos. La carga de calificaciones tarda unos minutos.
6. **Función Lambda:**
   - Nombre `recing-recommend`, runtime Python 3.12, en `us-east-1`.
   - Pega el contenido de `aws/lambda_function.py`.
   - Timeout de 30 s y memoria de 256 MB.
   - Variable de entorno `ENDPOINT_NAME=recing-fm-endpoint`.
   - Al rol de la función agrega `AWSLambdaBasicExecutionRole` (logs en CloudWatch) y esta política con permisos mínimos (reemplaza `<ACCOUNT_ID>`):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"],
         "Resource": [
           "arn:aws:dynamodb:us-east-1:<ACCOUNT_ID>:table/recing_users",
           "arn:aws:dynamodb:us-east-1:<ACCOUNT_ID>:table/recing_movies",
           "arn:aws:dynamodb:us-east-1:<ACCOUNT_ID>:table/recing_ratings"
         ]
       },
       {
         "Effect": "Allow",
         "Action": "sagemaker:InvokeEndpoint",
         "Resource": "arn:aws:sagemaker:us-east-1:<ACCOUNT_ID>:endpoint/recing-fm-endpoint"
       }
     ]
   }
   ```

## Cómo ejecutar el proyecto

### 1. Obtener el dataset

Descarga MovieLens 100K desde [GroupLens](https://grouplens.org/datasets/movielens/100k/) y descomprímelo en `data/ml-100k/`. Los archivos de datos no se versionan.

### 2. Entrenar el modelo (notebook)

```bash
jupyter notebook
```

Abre `notebooks/entrenamiento.ipynb`, edita `BUCKET` y `ROLE_ARN` en la primera celda y ejecuta las celdas en orden: exploración, split, baseline, subida a S3, conversión a recordIO-protobuf y entrenamiento en SageMaker. Al terminar, el modelo queda guardado en `s3://<tu-bucket>/fm/output/`.

> Si el entrenamiento falla con `ResourceLimitExceeded`, solicita en *Service Quotas* un aumento de `ml.m5.large for training job usage` (cuentas nuevas la traen en 0).

### 3. Desplegar el endpoint

```bash
python src/endpoint.py deploy              # instancia ml.m5.large (cobra por hora)
python src/endpoint.py deploy-serverless   # endpoint serverless (cobra por uso)
python src/endpoint.py status              # estado actual
python src/endpoint.py delete              # elimina el endpoint y su configuración
```

El script toma el último entrenamiento completado, por lo que no hace falta reentrenar para volver a desplegar. El endpoint tarda de 5 a 10 minutos en quedar en estado `InService`.

> **Costo:** un endpoint con instancia cobra por cada hora que existe, aunque no reciba solicitudes (~0.12 USD/hora para `ml.m5.large`). Ejecuta `python src/endpoint.py delete` al terminar cada sesión y verifica con `aws sagemaker list-endpoints --region us-east-1`.

### 4. Probar la Lambda (opcional)

```bash
python src/test_lambda.py
```

O desde la consola de Lambda, con el evento de prueba `{"user_id": 1, "top_n": 5}`.

### 5. Usar la CLI

```bash
python src/main.py
```

```
===== Rec'ing Movies AI =====
 1. Registrar usuario
 2. Iniciar sesión
 3. Buscar películas
 4. Calificar una película
 5. Ver mis calificaciones
 6. Obtener recomendaciones
 0. Salir
```

Ejemplo de demostración:

1. Inicia sesión como usuario `1` y pide recomendaciones.
2. Inicia sesión como usuario `200` y compara: las listas son distintas.
3. Califica con 5 la primera película recomendada y pide recomendaciones de nuevo: esa película ya no aparece.
4. Registra un usuario nuevo y pide recomendaciones: recibirá las más populares.

Sin el endpoint activo, las opciones 1 a 5 funcionan con normalidad y la opción 6 muestra películas populares con un aviso.

> El catálogo corresponde a MovieLens 100K (películas hasta 1998). La búsqueda por título distingue ortografía, por ejemplo `schindler`, no `schlinder`.

---

## Seguridad

**No se suben credenciales, claves de acceso ni secretos de AWS a este repositorio.** Boto3 y AWS CLI leen las credenciales de la configuración local (`aws configure`). El archivo `.gitignore` excluye `data/`, `*.csv`, `.env`, `*.pem` y el entorno virtual. Los permisos de Lambda siguen el principio de mínimo privilegio.

## Limitaciones y trabajo futuro

- El modelo solo conoce a los usuarios 1 a 943 y las películas 1 a 1,682. Reentrenar con las calificaciones nuevas de DynamoDB permitiría personalizar a usuarios nuevos.
- Calificar una película no modifica el modelo; solo la excluye de futuras recomendaciones hasta el siguiente reentrenamiento.
- Probar un endpoint serverless permanente para eliminar el costo por hora.
- Agregar métricas de ranking (Precision@K) y una interfaz web.

## Tecnologías

Python · Boto3 · Pandas · NumPy · scikit-learn · Amazon SageMaker · Amazon S3 · Amazon DynamoDB · AWS Lambda · AWS IAM · Amazon CloudWatch · Git y GitHub.
