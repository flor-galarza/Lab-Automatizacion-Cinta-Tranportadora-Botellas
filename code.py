# code.py — CircuitPython (Raspberry Pi Pico 2W)

import time
import board
import digitalio
import pwmio

# ============================
# Config generales / Utiles
# ============================
SEG_ON = True        # Si tu 7 segmentos es cátodo común => True. Si es ánodo común => False
IR_ACTIVE_LOW = True # Muchos sensores IR dan LOW cuando detectan

def now_s():
    return time.monotonic()

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
bottle_speeds = {1:0.2,2:0.4,3:0.3,4:0.6,5:0.5}
bottle_sizes  = {1:0.05,2:0.08,3:0.06,4:0.1,5:0.07}
bottle_index = 0

selected_mode = False
paused = False
error_state = False
encoder_press_count = 0

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
        if modes[mode_index]==1:
            # Manual: la primera botella inicia cronómetro (amarillo ya está desde la capa global)
            if first_manual_detection is None:
                if ir_detected():
                    first_manual_detection = now_s()
                    print(f"Primera botella detectada en t={first_manual_detection:.2f}s")
                    while ir_detected():
                        time.sleep(0.005)

            # A la espera de la segunda botella para medir intervalo (sigue amarillo)
            elif reference_time is None:
                if ir_detected():
                    second_time = now_s()
                    reference_time = (second_time - first_manual_detection)
                    print(f"Segunda botella detectada en t={second_time:.2f}s → intervalo regular={reference_time:.2f}s")
                    # al tener referencia, la capa global pasará a verde
                    while ir_detected():
                        time.sleep(0.005)

            else:
                # Ya regulado → verde (según capa global)
                if ir_detected():
                    t = now_s()
                    print(f"Botella detectada en t={t:.2f}s")
                    if t2 is not None:
                        elapsed = (t - t2)
                        if abs(elapsed - reference_time) > 2:
                            print("¡Atasco crítico detectado en modo Manual!")
                            error_state = True
                            encoder_press_count = 0
                    t2 = t

        else:
            # Automático
            bt = bottle_types[bottle_index]
            expected_interval = bottle_sizes[bt] / bottle_speeds[bt]
            if ir_detected():
                t_now = now_s()
                print(f"Botella detectada en t={t_now:.2f}s")
                if last_detection is not None:
                    elapsed = (t_now - last_detection)
                    if abs(elapsed - expected_interval) > 2:
                        print(f"¡Atasco crítico detectado en modo Automático! Intervalo esperado: {expected_interval:.2f}s, real: {elapsed:.2f}s")
                        error_state = True
                        encoder_press_count = 0
                last_detection = t_now

    time.sleep(0.05)
