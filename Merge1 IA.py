# code.py — CircuitPython (Raspberry Pi Pico 2W)
# MERGE: mantiene NETWORKING/MQTT del 1er código + agrega detección de atascos extendida del 2do

import time
import board
import digitalio
import pwmio
import wifi
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import json

# ============================
# Configuración de RED / MQTT
# ============================
SSID = "wfrre-Docentes"
PASSWORD = "20$tscFrre.24"
BROKER = "10.13.100.92"
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

pool = socketpool.SocketPool(wifi.radio)

def on_connect(client, userdata, flags, rc):
    print("Conectado al broker MQTT")
    discovery_msg = {"equipo": NOMBRE_EQUIPO, "magnitudes": ["estado", "velocidad", "modo"]}
    client.publish(DESCOVERY_TOPIC, json.dumps(discovery_msg))

mqtt_client = MQTT.MQTT(
    broker=BROKER,
    port=1883,
    socket_pool=pool,
    socket_timeout=5.0,  # mantener coherente con loop
    keep_alive=60
)
mqtt_client.on_connect = on_connect

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
            print("No se pudo conectar. Reiniciando en 5 segundos...")
            time.sleep(5)
            import supervisor
            supervisor.reload()

last_pub = 0
PUB_INTERVAL = 2  # s

# ============================
# Config generales / Utiles
# ============================
SEG_ON = True        # Display: cátodo común => True; ánodo común => False
IR_ACTIVE_LOW = True # Muchos sensores IR dan LOW cuando detectan

def now_s():
    return time.monotonic()

# ============================
# UMBRALES ATASCO (extendidos)
# ============================
EXPECTED_BOTTLE_INTERVAL_S = 2.0
INTERVAL_TOLERANCE_S = 0.3
AUTO_INTERVAL_TOLERANCE_S = 0.1
SENSOR_STALL_TIMEOUT_S = 5.0
NO_BOTTLE_TIMEOUT_EXTRA_S = 0.0

# ============================
# Display 7 segmentos
# ============================
def _out_pin(gp):
    p = digitalio.DigitalInOut(gp)
    p.direction = digitalio.Direction.OUTPUT
    p.value = not SEG_ON
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
    if color == 'normal':      # verde
        led_r.duty_cycle = 0
        led_g.duty_cycle = 65535
        led_b.duty_cycle = 0
    elif color == 'selecting': # azul
        led_r.duty_cycle = 0
        led_g.duty_cycle = 0
        led_b.duty_cycle = 65535
    elif color == 'yellow':    # amarillo
        led_r.duty_cycle = 65535
        led_g.duty_cycle = 40000
        led_b.duty_cycle = 0
    elif color == 'error':     # rojo parpadeante
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
bottle_speeds = {1:0.2,2:0.4,3:0.3,4:0.6,5:0.5}
bottle_sizes  = {1:0.05,2:0.08,3:0.06,4:0.1,5:0.07}
bottle_index = 0

selected_mode = False
paused = False
error_state = False
encoder_press_count = 0

# ======= Estado sensor / tiempos extendidos (merge del 2do código)
last_ir_level = None
last_state_change_time = None
last_bottle_time = None
auto_armed = False
auto_first_detection = None

# ======= Tiempos Manual/Automático
first_manual_detection = None
reference_time = None
t2 = None

last_detection = None

# ============================
# UI Selección
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
            selecting = False
            time.sleep(0.3)
        time.sleep(0.05)

def select_bottle():
    global bottle_index, last_clk, auto_armed, auto_first_detection, last_detection, last_bottle_time, last_state_change_time
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
            # Armar conteo automático desde la primera botella tras confirmar
            auto_armed = True
            auto_first_detection = None
            last_detection = None
            last_bottle_time = None
            last_state_change_time = now_s()
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
# Networking helpers (MQTT)
# ============================
def compute_state():
    """ Devuelve estado textual para publicar """
    if error_state:
        return "Atasco"
    if paused or not selected_mode:
        return "Seleccionando"
    if modes[mode_index] == 1:
        if first_manual_detection is None or reference_time is None:
            return "Regulando"
        return "Funcionando"
    return "Funcionando"

def publish():
    global last_pub
    now = time.monotonic()
    if now - last_pub >= PUB_INTERVAL:
        try:
            estado = compute_state()
            if modes[mode_index] == 1:
                modo = True
                valor = velocities[vel_index]
            else:
                modo = False
                bt = bottle_types[bottle_index]
                valor = bottle_speeds[bt]
            mqtt_client.publish(f"{TOPIC}/estado", str(estado))
            mqtt_client.publish(f"{TOPIC}/velocidad", str(valor))
            mqtt_client.publish(f"{TOPIC}/modo", str(modo).lower())
            last_pub = now
        except Exception as e:
            print(f"Error publicando MQTT: {e}")

# ============================
# Bucle principal
# ============================
while True:
    t_now_loop = now_s()

    # Velocidad actual para reportes/tiempos
    if modes[mode_index] == 1:
        current_speed_mps = velocities[vel_index]
    else:
        bt_tmp = bottle_types[bottle_index]
        current_speed_mps = bottle_speeds[bt_tmp]

    # UI (LED + Display)
    if error_state:
        display_digit('E')
        set_led('error')
    else:
        if paused:
            set_led('selecting')
        else:
            if modes[mode_index] == 1 and (first_manual_detection is None or reference_time is None):
                set_led('yellow')
            else:
                set_led('normal')
        display_digit(vel_index + 1 if modes[mode_index]==1 else bottle_types[bottle_index])

    # Botón (pausa / acknowledge)
    if pressed(sw):
        if error_state:
            encoder_press_count += 1
            print(f"Botón presionado en error ({encoder_press_count}/3)")
            if encoder_press_count >= 3:
                error_state = False
                encoder_press_count = 0
                # reset manual
                first_manual_detection = None
                reference_time = None
                t2 = None
                # reset extended
                last_bottle_time = None
                last_state_change_time = now_s()
                auto_armed = (modes[mode_index] == 2)
                auto_first_detection = None
                last_detection = None
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
                    last_bottle_time = None
                    last_state_change_time = now_s()
                    auto_armed = False
                    auto_first_detection = None
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

    # ======= Detección de atascos extendida (merge del 2do código)
    if not error_state:
        if last_ir_level is None:
            last_ir_level = ir_detected()
            last_state_change_time = t_now_loop

        current_ir = ir_detected()
        prev_ir = last_ir_level
        edge_rise = (not prev_ir) and current_ir
        if current_ir != prev_ir:
            last_state_change_time = t_now_loop
            last_ir_level = current_ir

        if modes[mode_index]==1:
            # Manual
            if first_manual_detection is None:
                if edge_rise:
                    first_manual_detection = now_s()
                    print(f"Primera botella detectada en t={first_manual_detection:.2f}s")
            elif reference_time is None:
                if edge_rise:
                    second_time = now_s()
                    reference_time = (second_time - first_manual_detection)
                    print(f"Segunda botella detectada en t={second_time:.2f}s → intervalo regular={reference_time:.2f}s")
            else:
                if edge_rise and not error_state:
                    t = now_s()
                    print(f"Botella detectada en t={t:.2f}s")
                    if t2 is not None:
                        elapsed = (t - t2)
                        expected_interval = reference_time if reference_time is not None else EXPECTED_BOTTLE_INTERVAL_S
                        if elapsed > (expected_interval + INTERVAL_TOLERANCE_S):
                            print(f"¡Atasco: intervalo excedido en Manual! esperado≈{expected_interval:.2f}s, real={elapsed:.2f}s")
                            error_state = True
                            encoder_press_count = 0
                    t2 = t
                    last_bottle_time = t

                # Timeout por no llegada a tiempo
                if (not error_state) and (last_bottle_time is not None):
                    expected_interval = reference_time if reference_time is not None else EXPECTED_BOTTLE_INTERVAL_S
                    if (t_now_loop - last_bottle_time) > (expected_interval + INTERVAL_TOLERANCE_S + NO_BOTTLE_TIMEOUT_EXTRA_S):
                        print(f"¡Atasco: no se detectan botellas a tiempo en Manual! > {expected_interval + INTERVAL_TOLERANCE_S + NO_BOTTLE_TIMEOUT_EXTRA_S:.2f}s")
                        error_state = True
                        encoder_press_count = 0

        else:
            # Automático
            bt = bottle_types[bottle_index]
            expected_interval = bottle_sizes[bt] / bottle_speeds[bt]
            if auto_armed and not error_state:
                if edge_rise:
                    t_now = now_s()
                    print(f"Botella detectada en t={t_now:.2f}s (Auto)")
                    if auto_first_detection is None:
                        auto_first_detection = t_now
                        last_bottle_time = t_now
                    else:
                        elapsed = (t_now - auto_first_detection)
                        if elapsed > (expected_interval + AUTO_INTERVAL_TOLERANCE_S):
                            print(f"¡Atasco: intervalo excedido en Automático! esperado≈{expected_interval:.2f}s, real={elapsed:.2f}s")
                            error_state = True
                            encoder_press_count = 0
                        auto_first_detection = t_now
                        last_detection = t_now
                        last_bottle_time = t_now

                # Timeout por no llegada a tiempo (después de la primera detección)
                if (not error_state) and (auto_first_detection is not None) and (last_bottle_time is not None):
                    if (t_now_loop - last_bottle_time) > (expected_interval + AUTO_INTERVAL_TOLERANCE_S + NO_BOTTLE_TIMEOUT_EXTRA_S):
                        print(f"¡Atasco: no se detectan botellas a tiempo en Automático! > {expected_interval + INTERVAL_TOLERANCE_S + NO_BOTTLE_TIMEOUT_EXTRA_S:.2f}s")
                        error_state = True
                        encoder_press_count = 0

        # Sensor “stall”: sin cambios mucho tiempo (si ya hubo botellas y hay velocidad)
        if (not error_state) and (last_state_change_time is not None) and (last_bottle_time is not None) and (current_speed_mps > 0.0):
            if (t_now_loop - last_state_change_time) > SENSOR_STALL_TIMEOUT_S:
                print(f"¡Atasco de sensor (sin cambios) por > {SENSOR_STALL_TIMEOUT_S:.1f}s!")
                error_state = True
                encoder_press_count = 0

        # Forzar 0 m/s en error solo a nivel de reporte (no afecta tu PWM/actuador aquí)
        if error_state and current_speed_mps != 0.0:
            print("Forzando velocidad a 0 m/s por atasco")
            current_speed_mps = 0.0

    # ============================
    # MQTT: loop + publish
    # ============================
    try:
        # Debe ser >= socket_timeout para evitar ValueError en minimqtt
        mqtt_client.loop(5.5)
    except Exception:
        pass

    publish()

    time.sleep(0.01)  # 10 ms: responsivo para el IR
