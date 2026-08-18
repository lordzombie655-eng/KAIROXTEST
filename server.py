import gc
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Configuración de optimización de memoria
gc.enable()
gc.set_threshold(700, 10, 10)  # Agresiva recolección de basura para ahorrar RAM

# Constantes del Servidor
HOST = "0.0.0.0"
PORT = 8080
MAX_PLAYERS = 1200  # Límite estricto de jugadores online

# Control de concurrencia y estado del servidor
active_players_lock = threading.Lock()
active_players = set()  # Almacena IDs o tokens de jugadores conectados

# Caché en memoria para evitar lecturas repetidas de disco (Ahorra CPU y RAM)
DATABASE_CACHE = {}
DB_DIR = os.path.join("Next-Private-Server-main", "Data", "db_files")


def load_database_files():
  """Carga los archivos JSON esenciales en memoria de manera optimizada

  para lectura rápida sin saturar la RAM.
  """
  if not os.path.exists(DB_DIR):
    print(
        f"[AVISO] Directorio de base de datos no encontrado: {DB_DIR}. Usando"
        " caché vacío."
    )
    return

  for filename in os.listdir(DB_DIR):
    if filename.endswith(".json"):
      file_path = os.path.join(DB_DIR, filename)
      try:
        with open(file_path, "r", encoding="utf-8") as f:
          # Usamos objetos compactos para minimizar el espacio en RAM
          DATABASE_CACHE[filename] = json.load(f)
      except Exception as e:
        print(f"[ERROR] No se pudo cargar {filename}: {e}")

  print(
      f"[INFO] Base de datos cargada. Archivos en caché: {len(DATABASE_CACHE)}"
  )


class OptimizedServerHandler(BaseHTTPRequestHandler):

  def log_message(self, format, *args):
    # Desactivar logs detallados por solicitud para evitar overhead en CPU bajo alta concurrencia
    return

  def do_GET(self):
    global active_players

    client_ip = self.client_address[0]

    # 1. Verificar límite de jugadores online (1,200 máx)
    with active_players_lock:
      if (
          client_ip not in active_players
          and len(active_players) >= MAX_PLAYERS
      ):
        self.send_response(503)  # Service Unavailable por servidor lleno
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            b'{"error": "Servidor lleno. Maximo de 1200 jugadores alcanzado."}'
        )
        return

    # 2. Enrutamiento básico y entrega de datos desde la caché
    if self.path.startswith("/api/get_db/"):
      db_name = self.path.split("/")[-1]
      target_file = f"db_{db_name}.json" if not db_name.endswith(".json") else db_name

      if target_file in DATABASE_CACHE:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        # Enviar directamente desde la caché RAM para máxima velocidad
        self.wfile.write(json.dumps(DATABASE_CACHE[target_file]).encode("utf-8"))
        return
      else:
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b'{"error": "Archivo de datos no encontrado."}')
        return

    # Respuesta por defecto (Health Check / Estado)
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    with active_players_lock:
      current_count = len(active_players)
    response_data = {
        "status": "online",
        "players_online": current_count,
        "max_players": MAX_PLAYERS,
    }
    self.wfile.write(json.dumps(response_data).encode("utf-8"))

  def do_POST(self):
    global active_players
    client_ip = self.client_address[0]

    content_length = int(self.headers.get("Content-Length", 0))
    post_data = self.read_body(content_length) if content_length > 0 else b""

    # Registrar conexión de jugador si intenta autenticarse o hacer handshake
    with active_players_lock:
      if client_ip not in active_players:
        if len(active_players) >= MAX_PLAYERS:
          self.send_response(503)
          self.end_headers()
          self.wfile.write(b'{"error": "Servidor al limite de capacidad."}')
          return
        active_players.add(client_ip)

    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(b'{"status": "success", "message": "Conectado al servidor"}')

  def read_body(self, length):
    # Lectura controlada para evitar desbordamiento de memoria por paquetes maliciosos
    if length > 65536:  < 64KB por paquete
      return b""
    return self.rfile.read(length)


def run_server():
  print("[INICIALIZANDO] Cargando archivos de base de datos en RAM...")
  load_database_files()

  server_address = (HOST, PORT)
  httpd = HTTPServer(server_address, OptimizedServerHandler)
  print(
      f"[OK] Servidor optimizado corriendo en {HOST}:{PORT} | Límite:"
      f" {MAX_PLAYERS} jugadores."
  )

  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    print("\n[INFO] Apagando servidor...")
    httpd.server_close()


if __name__ == "__main__":
  run_server()
 
