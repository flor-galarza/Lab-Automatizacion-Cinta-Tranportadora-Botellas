# code.py — CircuitPython (Raspberry Pi Pico 2W)

import time
import board
import digitalio
import pwmio
import wifi
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import json

# Configuración de RED
SSID = "wfrre-Docentes"
PASSWORD = "20$tscFrre.24"
BROKER = "10.13.100.72"  
NOMBRE_EQUIPO = "CortoCircuito"
DESCOVERY_TOPIC = "descubrir"
TOPIC = f"sensores/{NOMBRE_EQUIPO}"

print(f"Intentando conectar a {SSID}...")
try:
    wifi.radio.connect(SSID, PASSWORD)
    print(f"Conectado a {SSID}")
    print(f"Dirección IP: {wifi.radio.ipv4_address}")
except Exception as e:
    print(f"Error al conectar a WiFi: {e}")
    while True:
        pass 

# Configuración MQTT 
pool = socketpool.SocketPool(wifi.radio)

def connect(client, userdata, flags, rc):
    print("Conectado al broker MQTT")
    # Anunciamos qué magnitudes publica este equipo (incluye 'estado')
    discovery_msg = {"equipo": NOMBRE_EQUIPO, "magnitudes": ["estado", "velocidad", "modo"]}
    client.publish(DESCOVERY_TOPIC, json.dumps(discovery_msg))

mqtt_client = MQTT.MQTT(
    broker=BROKER,
    port=1883,
    socket_pool=pool,
    socket_timeout=5.0,  # Timeout más generoso para conexiones lentas
    keep_alive=60
)
mqtt_client.on_connect = connect

# Conectar con reintentos manuales
print("Conectando a MQTT...")
max_retries = 5
retry_count = 0
connected = False

while not connected and retry_count < max_retries:
    try:
        print(f"Intento {retry_count + 1}/{max_retries}...")
        mqtt_client.connect()
        connected = True
        print("Conectado al broker MQTT exitosamente")
    except Exception as e:
        retry_count += 1
        print(f"Error de conexión: {e}")
        if retry_count < max_retries:
            print("Esperando 3 segundos...")
            time.sleep(3)
        else:
            print("No se pudo conectar después de todos los intentos")
            print("Reiniciando en 5 segundos...")
            time.sleep(5)
            import supervisor
            supervisor.reload()

# Usamos estas variables globales para controlar cada cuánto publicamos
last_pub = 0
PUB_INTERVAL = 2  # segundos - reducido de 5 a 2 para mejor balance

def compute_state():
    """
    Devuelve el estado textual del sistema:
    - 'Funcionando'   -> LED verde
    - 'Atasco'        -> LED rojo titilando
    - 'Regulando'     -> LED amarillo (manual sin referencia aún)
    - 'Seleccionando' -> LED azul (menús/pausa)
    """
    # Estado de error (atasco) manda primero
    if error_state:
        return "Atasco"

    # Menús de selección o pausa usan el LED azul
    # (en tu lógica, 'paused' muestra azul y durante select_* también)
    if paused or not selected_mode:
        return "Seleccionando"

    # Manual: hasta que haya referencia (first_manual_detection y reference_time) está en amarillo
    if modes[mode_index] == 1:
        if first_manual_detection is None or reference_time is None:
            return "Regulando"
        return "Funcionando"

    # Automático corre en verde
    return "Funcionando"


def publish():
    global last_pub
    now = time.monotonic()
    if now - last_pub >= PUB_INTERVAL:
        try:
            estado = compute_state()

            # Armamos payload útil (modo+valor característico)
            if error_state:
                # En caso de atasco, velocidad = 0
                valor = 0.0
                modo = True if modes[mode_index] == 1 else False
            else:
                if modes[mode_index] == 1:
                    modo = True
                    valor = velocities[vel_index]  # m/s
                else:
                    modo = False
                    bt = bottle_types[bottle_index]
                    valor = bottle_speeds[bt]      # m/s

            # Publicar de forma más eficiente
            estado_topic = f"{TOPIC}/estado"
            velocidad_topic = f"{TOPIC}/velocidad"
            modo_topic = f"{TOPIC}/modo"
            
            # Publicar todos los mensajes de una vez
            mqtt_client.publish(estado_topic, str(estado))
            mqtt_client.publish(velocidad_topic, str(valor))
            mqtt_client.publish(modo_topic, str(modo).lower())
            
            last_pub = now

        except Exception as e:
            print(f"Error publicando MQTT: {e}")

def publish_serial_velocity():
    """
    Publica la velocidad actual por puerto serial para monitoreo.
    Si hay atasco, la velocidad se reporta como 0.
    """
    if error_state:
        # En caso de atasco, velocidad = 0
        velocidad_serial = 0.0
    else:
        # Velocidad normal según el modo
        if modes[mode_index] == 1:
            velocidad_serial = velocities[vel_index]  # m/s
        else:
            bt = bottle_types[bottle_index]
            velocidad_serial = bottle_speeds[bt]      # m/s
    
    # Publicar por puerto serial para el plotter
    print(f"VELOCIDAD:{velocidad_serial:.2f}")



# ============================
# Config generales / Utiles
# ============================
SEG_ON = True        # Si tu 7 segmentos es cátodo común => True. Si es ánodo común => False
IR_ACTIVE_LOW = True # Muchos sensores IR dan LOW cuando detectan

def now_s():
    return time.monotonic()

# ============================
# Umbrales de atasco (AJUSTABLES)
# ============================
# Intervalo esperado global si no hay referencia calculada (Manual) o como base de monitoreo
EXPECTED_BOTTLE_INTERVAL_S = 2.0
# Tolerancia permitida contra el intervalo esperado (se suma al esperado)
INTERVAL_TOLERANCE_S = 1.0
# Tolerancia específica para modo Automático (±1.0 s)
AUTO_INTERVAL_TOLERANCE_S = 1.0
# Si no hay cambios en el estado del sensor (siempre en 1 o siempre en 0) por más de este tiempo → atasco
SENSOR_STALL_TIMEOUT_S = 30.0  # Aumentado para que no interfiera con el timeout correcto
# Cuando hay intervalo esperado (manual ya regulado o automático), si se supera esperado + tolerancia → atasco
NO_BOTTLE_TIMEOUT_EXTRA_S = 5.0  # extra opcional al esperado (ahora 5s sobre el intervalo regular)

# Intervalo esperado fijo por tipo de botella en Automático (1→1s, 2→2s, ..., 5→5s)
BOTTLE_EXPECTED_INTERVAL_S = {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0, 5: 5.0}

# ============================
# Display 7 segmentos
# ============================
def _out_pin(gp):
    p = digitalio.DigitalInOut(gp)
    p.direction = digitalio.Direction.OUTPUT
    p.value = not SEG_ON  # apagado por defecto
    return p

segments = {
    'A': _out_pin(board.GP3),
    'B': _out_pin(board.GP4),
    'C': _out_pin(board.GP5),
    'D': _out_pin(board.GP6),
    'E': _out_pin(board.GP7),
    'F': _out_pin(board.GP8),
    'G': _out_pin(board.GP9),
}

digit_patterns = {
    0: ['A','B','C','D','E','F'],
    1: ['B','C'],
    2: ['A','B','D','E','G'],
    3: ['A','B','C','D','G'],
    4: ['B','C','F','G'],
    5: ['A','C','D','F','G'],
    6: ['A','C','D','E','F','G'],
    7: ['A','B','C'],
    8: ['A','B','C','D','E','F','G'],
    9: ['A','B','C','D','F','G'],
    'E': ['A','D','E','F','G']  # Error
}

def display_digit(digit):
    for pin in segments.values():
        pin.value = not SEG_ON
    for seg_name in digit_patterns[digit]:
        segments[seg_name].value = SEG_ON

# ============================
# LED RGB (PWM)
# ============================
led_r = pwmio.PWMOut(board.GP0, frequency=1000, duty_cycle=0)
led_g = pwmio.PWMOut(board.GP1, frequency=1000, duty_cycle=0)
led_b = pwmio.PWMOut(board.GP2, frequency=1000, duty_cycle=0)

error_blink = False
last_blink_time = now_s()

def set_led(color):
    global error_blink, last_blink_time
    if color == 'normal':  # verde
        led_r.duty_cycle = 0
        led_g.duty_cycle = 65535
        led_b.duty_cycle = 0
    elif color == 'selecting':  # azul
        led_r.duty_cycle = 0
        led_g.duty_cycle = 0
        led_b.duty_cycle = 65535
    elif color == 'yellow':  # amarillo balanceado (más verde)
        led_r.duty_cycle = 65535
        led_g.duty_cycle = 40000
        led_b.duty_cycle = 0


    elif color == 'error':  # rojo parpadeante
        t = now_s()
        if (t - last_blink_time) > 0.3:
            error_blink = not error_blink
            last_blink_time = t
        if error_blink:
            led_r.duty_cycle = 65535
            led_g.duty_cycle = 0
            led_b.duty_cycle = 0
        else:
            led_r.duty_cycle = 0
            led_g.duty_cycle = 0
            led_b.duty_cycle = 0

# ============================
# Entradas: Encoder + Botón
# ============================
def _in_pin(gp, pull_up=True):
    p = digitalio.DigitalInOut(gp)
    p.direction = digitalio.Direction.INPUT
    p.pull = digitalio.Pull.UP if pull_up else None
    return p

clk = _in_pin(board.GP12, pull_up=True)
dt  = _in_pin(board.GP11, pull_up=True)
sw  = _in_pin(board.GP10, pull_up=True)
last_clk = clk.value

# ============================
# Sensor IR
# ============================
ir = _in_pin(board.GP13, pull_up=False)

def ir_detected():
    v = ir.value  # True=alto, False=bajo
    return (not v) if IR_ACTIVE_LOW else v

# ============================
# Variables de control
# ============================
modes = [1, 2]   # 1=Manual, 2=Automático
mode_index = 0

velocities = [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9]
vel_index = 4

bottle_types  = [1,2,3,4,5]
bottle_speeds = {1:0.2,2:0.4,3:0.6,4:0.8,5:1.0}
bottle_sizes  = {1:0.05,2:0.08,3:0.06,4:0.1,5:0.07}
bottle_index = 0

selected_mode = False
paused = False
error_state = False
encoder_press_count = 0

# ============================
# Estado de sensor / tiempos
# ============================
last_ir_level = None
last_state_change_time = None
last_bottle_time = None

# Armado de medición en modo Automático (se activa al confirmar selección con el botón)
auto_armed = False
auto_first_detection = None

# ============================
# Tiempo Manual
# ============================
first_manual_detection = None
reference_time = None
t2 = None

# ============================
# Tiempo Automático
# ============================
last_detection = None

# ============================
# Funciones de selección
# ============================
def pressed(btn):
    return sw.value == False  # Pull.UP -> presionado = False

def select_mode():
    global mode_index, last_clk, selected_mode
    while not selected_mode:
        display_digit(modes[mode_index])
        set_led('selecting')

        clk_val = clk.value
        if clk_val != last_clk:
            if dt.value != clk_val:
                mode_index = (mode_index + 1) % len(modes)
            else:
                mode_index = (mode_index - 1) % len(modes)
        last_clk = clk_val

        if pressed(sw):
            selected_mode = True
            print("Modo seleccionado:", "Manual" if modes[mode_index]==1 else "Automático")
            # Publicar velocidad inicial por serial
            publish_serial_velocity()
            time.sleep(0.3)
        time.sleep(0.05)

def select_velocity():
    global vel_index, last_clk
    selecting = True
    while selecting:
        display_digit(vel_index + 1)
        set_led('selecting')

        clk_val = clk.value
        if clk_val != last_clk:
            if dt.value != clk_val:
                vel_index = min(vel_index + 1, len(velocities)-1)
            else:
                vel_index = max(vel_index - 1, 0)
        last_clk = clk_val

        if pressed(sw):
            print("Velocidad seleccionada:", velocities[vel_index], "m/s")
            # Publicar nueva velocidad por serial
            publish_serial_velocity()
            selecting = False
            time.sleep(0.3)
        time.sleep(0.05)

def select_bottle():
    global bottle_index, last_clk
    selecting = True
    while selecting:
        display_digit(bottle_types[bottle_index])
        set_led('selecting')

        clk_val = clk.value
        if clk_val != last_clk:
            if dt.value != clk_val:
                bottle_index = (bottle_index + 1) % len(bottle_types)
            else:
                bottle_index = (bottle_index - 1) % len(bottle_types)
        last_clk = clk_val

        if pressed(sw):
            bt = bottle_types[bottle_index]
            print(f"Botella seleccionada: {bt}, velocidad: {bottle_speeds[bt]} m/s")
            # Publicar nueva velocidad por serial
            publish_serial_velocity()
            # Armar conteo automático desde la PRIMERA botella tras confirmar
            global auto_armed, auto_first_detection, last_detection, last_bottle_time, last_state_change_time
            auto_armed = True
            auto_first_detection = None
            last_detection = None
            # Iniciar conteo de timeout inmediatamente al armar (sin esperar primera botella)
            last_bottle_time = now_s()
            last_state_change_time = last_bottle_time
            # En Automático, activar timeout inmediatamente sin esperar primera detección
            auto_first_detection = now_s()  # Simular primera detección para activar timeout
            selecting = False
            time.sleep(0.3)
        time.sleep(0.05)

# ============================
# Selección inicial
# ============================
select_mode()
if modes[mode_index] == 1:
    select_velocity()
else:
    select_bottle()

# ============================
# Programa principal
# ============================
while True:    
    t_now_loop = now_s()
    # Mostrar display y color "global" según estado
    if error_state:
        display_digit('E')
        set_led('error')
    else:
        # Si está pausado → azul
        if paused:
            set_led('selecting')
        else:
            # Si está en Manual y aún no reguló (no tiene referencia):
            if modes[mode_index] == 1 and (first_manual_detection is None or reference_time is None):
                set_led('yellow')   # comienza y permanece amarillo hasta regular
            else:
                set_led('normal')   # verde
        display_digit(vel_index + 1 if modes[mode_index]==1 else bottle_types[bottle_index])

    # ------- Pause / Reconfiguración -------
    if pressed(sw):
        if error_state:
            encoder_press_count += 1
            print(f"Botón presionado en estado de error ({encoder_press_count}/3)")
            if encoder_press_count >= 3:
                error_state = False
                encoder_press_count = 0
                first_manual_detection = None
                reference_time = None
                t2 = None
                last_state_change_time = now_s()
                auto_armed = (modes[mode_index] == 2)
                auto_first_detection = None
                last_detection = None
                # Reiniciar timeout correctamente según el modo
                if modes[mode_index] == 2:  # Automático
                    last_bottle_time = now_s()  # Iniciar timeout inmediatamente
                    auto_first_detection = now_s()  # Simular primera detección
                else:  # Manual
                    last_bottle_time = None  # No iniciar hasta tener referencia
                print("Error resuelto, sistema reanudado.")
        else:
            paused = not paused
            if paused:
                print("Sistema pausado. Gira encoder para cambiar modo o parámetros.")
            else:
                if modes[mode_index]==1:
                    first_manual_detection = None
                    reference_time = None
                    t2 = None
                    last_bottle_time = None  # No iniciar timeout hasta estar en "Funcionando"
                    last_state_change_time = now_s()
                    auto_armed = False
                    auto_first_detection = None
                else:  # Automático
                    last_bottle_time = now_s()  # Iniciar timeout inmediatamente
                    last_state_change_time = now_s()
                    auto_armed = True
                    auto_first_detection = now_s()  # Simular primera detección
                print("Sistema reanudado.")
        time.sleep(0.3)

    while paused:
        selected_mode = False
        select_mode()
        if modes[mode_index]==1:
            select_velocity()
        else:
            select_bottle()
        paused = False

    # ------- Detección de atascos -------
    if not error_state:
        # Inicializar seguimiento de estado del IR
        if last_ir_level is None:
            last_ir_level = ir_detected()
            last_state_change_time = t_now_loop

        # Edge detection: flanco de subida (no detectado -> detectado)
        current_ir = ir_detected()
        prev_ir = last_ir_level
        edge_rise = (not prev_ir) and current_ir
        if current_ir != prev_ir:
            last_state_change_time = t_now_loop
            last_ir_level = current_ir

        if modes[mode_index]==1:
            # Manual: la primera botella inicia cronómetro (amarillo ya está desde la capa global)
            if first_manual_detection is None:
                if edge_rise:
                    first_manual_detection = now_s()
                    print(f"Primera botella detectada en t={first_manual_detection:.2f}s")
                    # a partir de aquí la capa global pasará a verde cuando haya referencia

            # A la espera de la segunda botella para medir intervalo (sigue amarillo)
            elif reference_time is None:
                if edge_rise:
                    second_time = now_s()
                    reference_time = (second_time - first_manual_detection)
                    print(f"Segunda botella detectada en t={second_time:.2f}s → intervalo regular={reference_time:.2f}s")
                    # al tener referencia, la capa global pasará a verde
                    # Iniciar timeout desde el momento de obtener referencia
                    last_bottle_time = second_time

            else:
                # Ya regulado → verde (según capa global)
                if edge_rise and not error_state:
                    t = now_s()
                    print(f"Botella detectada en t={t:.2f}s")
                    if t2 is not None:
                        elapsed = (t - t2)
                        expected_interval = reference_time if reference_time is not None else EXPECTED_BOTTLE_INTERVAL_S
                        min_interval = expected_interval - INTERVAL_TOLERANCE_S
                        max_interval = expected_interval + INTERVAL_TOLERANCE_S
                        if elapsed < min_interval or elapsed > max_interval:
                            print(f"¡Atasco: intervalo fuera de rango en Manual! esperado≈{expected_interval:.2f}s±{INTERVAL_TOLERANCE_S:.1f}s, real={elapsed:.2f}s")
                            error_state = True
                            encoder_press_count = 0
                    t2 = t
                    last_bottle_time = t

                # Timeout por no llegada de botella a tiempo (intervalo regular + 5s)
                # En Manual: solo activar cuando está en estado "Funcionando" (ya tiene referencia)
                if (not error_state) and (reference_time is not None) and (last_bottle_time is not None):
                    expected_interval = reference_time
                    timeout_threshold = expected_interval + NO_BOTTLE_TIMEOUT_EXTRA_S
                    elapsed_since_last = t_now_loop - last_bottle_time
                    # Debug cada 10 segundos
                    if int(t_now_loop) % 10 == 0:
                        print(f"DEBUG Manual: elapsed={elapsed_since_last:.2f}s, threshold={timeout_threshold:.2f}s, reference={reference_time:.2f}s")
                    if elapsed_since_last > timeout_threshold:
                        print(f"¡Atasco: no se detectan botellas a tiempo en Manual! > {timeout_threshold:.2f}s (intervalo: {expected_interval:.2f}s + 5s)")
                        print(f"DEBUG: tiempo transcurrido: {elapsed_since_last:.2f}s, umbral: {timeout_threshold:.2f}s")
                        error_state = True
                        encoder_press_count = 0

        else:
            # Automático
            bt = bottle_types[bottle_index]
            # Intervalo esperado fijo según tipo de botella (1→1s, ..., 5→5s)
            expected_interval = BOTTLE_EXPECTED_INTERVAL_S.get(bt, EXPECTED_BOTTLE_INTERVAL_S)
            if auto_armed and not error_state:
                if edge_rise:
                    t_now = now_s()
                    print(f"Botella detectada en t={t_now:.2f}s (Auto)")
                    # Actualizar tiempo de última botella
                    last_bottle_time = t_now
                    # Si es la primera detección real, actualizar auto_first_detection
                    if auto_first_detection is not None:
                        # Medir intervalo desde la anterior
                        elapsed = (t_now - auto_first_detection)
                        min_interval = expected_interval - AUTO_INTERVAL_TOLERANCE_S
                        max_interval = expected_interval + AUTO_INTERVAL_TOLERANCE_S
                        if elapsed < min_interval or elapsed > max_interval:
                            print(f"¡Atasco: intervalo fuera de rango en Automático! esperado≈{expected_interval:.2f}s±{AUTO_INTERVAL_TOLERANCE_S:.1f}s, real={elapsed:.2f}s")
                            error_state = True
                            encoder_press_count = 0
                    # Actualizar referencias para siguiente intervalo
                    auto_first_detection = t_now
                    last_detection = t_now

                # Timeout por no llegada de botella a tiempo (intervalo regular + 5s)
                # En Automático: activar inmediatamente al armar
                if (not error_state) and (last_bottle_time is not None):
                    timeout_threshold = expected_interval + NO_BOTTLE_TIMEOUT_EXTRA_S
                    elapsed_since_last = t_now_loop - last_bottle_time
                    # Debug cada 10 segundos
                    if int(t_now_loop) % 10 == 0:
                        print(f"DEBUG Auto: elapsed={elapsed_since_last:.2f}s, threshold={timeout_threshold:.2f}s, expected={expected_interval:.2f}s")
                    if elapsed_since_last > timeout_threshold:
                        print(f"¡Atasco: no se detectan botellas a tiempo en Automático! > {timeout_threshold:.2f}s (intervalo: {expected_interval:.2f}s + 5s)")
                        print(f"DEBUG: tiempo transcurrido: {elapsed_since_last:.2f}s, umbral: {timeout_threshold:.2f}s")
                        error_state = True
                        encoder_press_count = 0

        # Timeout por sensor atascado (sin cambios de estado mucho tiempo)
        # Solo aplicar si ya hubo al menos una botella detectada y la velocidad actual es > 0
        # Calcular velocidad actual seleccionada (solo para esta verificación)
        if modes[mode_index] == 1:
            current_speed_mps = velocities[vel_index]
        else:
            bt_tmp = bottle_types[bottle_index]
            current_speed_mps = bottle_speeds[bt_tmp]

        if (not error_state) and (last_state_change_time is not None) and (last_bottle_time is not None) and (current_speed_mps > 0.0):
            if (t_now_loop - last_state_change_time) > SENSOR_STALL_TIMEOUT_S:
                print(f"¡Atasco de sensor (sin cambios) por > {SENSOR_STALL_TIMEOUT_S:.1f}s!")
                error_state = True
                encoder_press_count = 0

        # Forzar velocidad a 0 en atasco (solo para reporte serial)
        if error_state:
            # Nota: no modificamos publicación ni control de motor; solo mensaje
            pass

    # MQTT solo cada cierto tiempo para no interferir con el sensor IR
    # Solo procesar MQTT si no estamos en un estado crítico de detección
    try:
        mqtt_client.loop(1.0)  # Debe ser >= socket_timeout (5.0)
    except Exception:
        pass  # Silenciar errores de MQTT loop
    publish()
    
    # Monitoreo por puerto serial de velocidad para el plotter
    publish_serial_velocity()

    time.sleep(0.05)



