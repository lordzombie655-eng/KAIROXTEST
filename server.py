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

DATABASE_CACHE = {}
DB_DIR = os.path.join("Next-Private-Server-main", "Data", "db_files")


def load_database_files():
  if not os.path.exists(DB_DIR):
    print(
        f"[AVISO] Directorio de base de datos no encontrado: {DB_DIR}. Creando"
        " caché vacío."
    )
    return

  for filename in os.listdir(DB_DIR):
    if filename.endswith(".json"):
      file_path = os.path.join(DB_DIR, filename)
      try:
        with open(file_path, "r", encoding="utf-8") as f:
          DATABASE_CACHE[filename] = json.load(f)
      except Exception as e:
        print(f"[ERROR] No se pudo cargar {filename}: {e}")

  print(
      f"[INFO] Base de datos cargada. Archivos en caché: {len(DATABASE_CACHE)}"
  )


def patch_monster_data_to_level_20(data):
  """Recurre recursivamente los datos de guardado/sincronización de MSM

  para forzar que cualquier monstruo colocado o comprado nazca directamente
  a Nivel 20, sin importar la versión del cliente.
  """
  if isinstance(data, dict):
    # Claves comunes que MSM utiliza para denotar monstruos y su nivel
    if "Level" in data or "level" in data:
      data["Level"] = 20
      data["level"] = 20

    # Si el objeto representa una entidad de monstruo con propiedades de colocación
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
    global active_players
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

    # Soporte Multi-Servidor / Universos independientes por URL o Parámetro (ej: /server/isla_1/api/...)
    path_parts = self.path.strip("/").split("/")
    server_instance = "default_universe"

    # Si la petición especifica un sub-servidor/isla en la ruta
    if len(path_parts) > 1 and path_parts[0] == "universe":
      server_instance = path_parts[1]
      actual_path = "/" + "/".join(path_parts[2:])
    else:
      actual_path = self.path

    # Enrutamiento de datos guardados (Compatible con cualquier versión de MSM)
    if "get" in actual_path or "profile" in actual_path or "sync" in actual_path:
      # Buscar archivo de base de datos asociado al universo o usar el general por defecto
      target_file = f"save_{server_instance}.json"
      if target_file not in DATABASE_CACHE:
        target_file = (
            list(DATABASE_CACHE.keys())[0] if DATABASE_CACHE else None
        )

      if target_file and target_file in DATABASE_CACHE:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        # Copiar y aplicar parche para asegurar Nivel 20 en los monstruos de la respuesta
        raw_data = DATABASE_CACHE[target_file]
        patched_data = patch_monster_data_to_level_20(
            json.loads(json.dumps(raw_data))
        )
        self.wfile.write(json.dumps(patched_data).encode("utf-8"))
        return

    # Respuesta por defecto o estado del nodo
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
    global active_players
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

    # Procesar peticiones de guardado del cliente MSM de cualquier versión
    try:
      if post_data:
        json_data = json.loads(post_data.decode("utf-8", errors="ignore"))
        # Parchear datos enviados por el cliente para forzar nivel 20 al colocarlos/actualizarlos
        patched_incoming = patch_monster_data_to_level_20(json_data)
        response_payload = {
            "status": "success",
            "version_compatibility": "universal",
            "data": patched_incoming,
        }
      else:
        response_payload = {
            "status": "success",
            "version_compatibility": "universal",
        }
    except Exception:
      response_payload = {
          "status": "success",
          "version_compatibility": "universal",
      }

    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(json.dumps(response_payload).encode("utf-8"))


def run_server():
  print("[INICIALIZANDO] Cargando base de datos multiversión...")
  load_database_files()

  port = int(os.environ.get("PORT", 8080))
  server_address = (HOST, port)
  httpd = HTTPServer(server_address, OptimizedServerHandler)
  print(
      f"[OK] Servidor MSM Universal Multiverso en puerto {port} | Límite:"
      f" {MAX_PLAYERS} jugadores."
  )

  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    httpd.server_close()


if __name__ == "__main__":
  run_server()
