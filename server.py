import gc
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Configuración de optimización de memoria para 1 GB de RAM
gc.enable()
gc.set_threshold(700, 10, 10)

HOST = "0.0.0.0"
PORT = 8080
MAX_PLAYERS = 1200

active_players_lock = threading.Lock()
active_players = set()

# Caché en memoria para la base de datos y perfiles
DATABASE_CACHE = {}
PLAYER_DATA = {}

# Rutas basadas en tu estructura de repositorio
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILES_DIR = os.path.join(
    BASE_DIR, "Data", "db_files"
)
PLAYER_JSON_PATH = os.path.join(BASE_DIR, "Data", "player.json")


def load_database_files():
  global PLAYER_DATA

  # 1. Cargar player.json
  if os.path.exists(PLAYER_JSON_PATH):
    try:
      with open(PLAYER_JSON_PATH, "r", encoding="utf-8") as f:
        PLAYER_DATA = json.load(f)
      print("[INFO] player.json cargado exitosamente.")
    except Exception as e:
      print(f"[ERROR] No se pudo cargar player.json: {e}")
  else:
    print(f"[AVISO] No se encontró player.json en la ruta: {PLAYER_JSON_PATH}")

  # 2. Cargar todos los archivos de db_files
  if not os.path.exists(DB_FILES_DIR):
    print(
        "[AVISO] Directorio db_files no encontrado en:"
        f" {DB_FILES_DIR}. Creando caché vacío."
    )
    return

  for filename in os.listdir(DB_FILES_DIR):
    if filename.endswith(".json"):
      file_path = os.path.join(DB_FILES_DIR, filename)
      try:
        with open(file_path, "r", encoding="utf-8") as f:
          DATABASE_CACHE[filename] = json.load(f)
      except Exception as e:
        print(f"[ERROR] No se pudo cargar {filename}: {e}")

  print(
      f"[INFO] Base de datos cargada. Archivos en caché: {len(DATABASE_CACHE)}"
  )


def patch_monster_data_to_level_20(data):
  """Recorre de forma recursiva los datos para forzar que cualquier

  monstruo colocado o sincronizado aparezca directamente a Nivel 20.
  """
  if isinstance(data, dict):
    if "Level" in data or "level" in data:
      data["Level"] = 20
      data["level"] = 20

    if (
        "MonsterID" in data
        or "monster_id" in data
        or "EntityId" in data
        or "torches" in data
    ):
      data["Level"] = 20
      if "level" in data:
        data["level"] = 20

    for key, value in data.items():
      data[key] = patch_monster_data_to_level_20(value)

  elif isinstance(data, list):
    for i, item in enumerate(data):
      data[i] = patch_monster_data_to_level_20(item)

  return data


class OptimizedServerHandler(BaseHTTPRequestHandler):

  def log_message(self, format, *args):
    return

  def do_GET(self):
    global active_players, PLAYER_DATA
    client_ip = self.client_address[0]

    with active_players_lock:
      if (
          client_ip not in active_players
          and len(active_players) >= MAX_PLAYERS
      ):
        self.send_response(503)
        self.end_headers()
        self.wfile.write(
            b'{"error": "Servidor lleno. Maximo de 1200 jugadores."}'
        )
        return

    # Enrutamiento Multi-Servidor / Universos e información de jugador
    path_parts = self.path.strip("/").split("/")
    server_instance = "default_universe"

    if len(path_parts) > 1 and path_parts[0] == "universe":
      server_instance = path_parts[1]
      actual_path = "/" + "/".join(path_parts[2:])
    else:
      actual_path = self.path

    # Si solicitan datos de jugador o perfiles, devolvemos player.json parcheado a nivel 20
    if "player" in actual_path or "profile" in actual_path:
      self.send_response(200)
      self.send_header("Content-Type", "application/json")
      self.end_headers()
      patched_player = patch_monster_data_to_level_20(
          json.loads(json.dumps(PLAYER_DATA))
      )
      self.wfile.write(json.dumps(patched_player).encode("utf-8"))
      return

    # Si solicitan archivos de base de datos generales
    if "get" in actual_path or "db" in actual_path:
      target_file = f"save_{server_instance}.json"
      if target_file not in DATABASE_CACHE and DATABASE_CACHE:
        target_file = list(DATABASE_CACHE.keys())[0]

      if target_file and target_file in DATABASE_CACHE:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        patched_data = patch_monster_data_to_level_20(
            json.loads(json.dumps(DATABASE_CACHE[target_file]))
        )
        self.wfile.write(json.dumps(patched_data).encode("utf-8"))
        return

    # Estado general del servidor
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(
        json.dumps({
            "status": "online",
            "universe": server_instance,
            "players": len(active_players),
        }).encode("utf-8")
    )

  def do_POST(self):
    global active_players, PLAYER_DATA
    client_ip = self.client_address[0]

    content_length = int(self.headers.get("Content-Length", 0))
    post_data = self.rfile.read(content_length) if content_length > 0 else b""

    with active_players_lock:
      if client_ip not in active_players:
        if len(active_players) >= MAX_PLAYERS:
          self.send_response(503)
          self.end_headers()
          return
        active_players.add(client_ip)

    try:
      if post_data:
        json_data = json.loads(post_data.decode("utf-8", errors="ignore"))
        patched_incoming = patch_monster_data_to_level_20(json_data)
        response_payload = {
            "status": "success",
            "compatibility": "universal",
            "data": patched_incoming,
        }
      else:
        response_payload = {"status": "success", "compatibility": "universal"}
    except Exception:
      response_payload = {"status": "success", "compatibility": "universal"}

    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(json.dumps(response_payload).encode("utf-8"))


def run_server():
  print("[INICIALIZANDO] Cargando recursos desde la carpeta Data...")
  load_database_files()

  port = int(os.environ.get("PORT", 8080))
  server_address = (HOST, port)
  httpd = HTTPServer(server_address, OptimizedServerHandler)
  print(
      f"[OK] Servidor MSM activo en puerto {port} | Límite: {MAX_PLAYERS}"
      " jugadores."
  )

  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    httpd.server_close()


if __name__ == "__main__":
  run_server()
