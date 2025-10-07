# Automatización de Cinta Transportadora de Botellas

Este proyecto consiste en el desarrollo de un sistema **inteligente** para monitorear y controlar una cinta transportadora de botellas, utilizando una Raspberry Pi Pico W, sensores y comunicación inalámbrica vía MQTT.

---

## 🌐 Diagrama de funcionamiento

El flujo del sistema puede ilustrarse de la siguiente manera:

```
+--------------------------+      +-------------------+      +-------------------+
|                          |      |                   |      |                   |
|   Encoder + Botón        +----->+  RPi Pico W (CPU) +----->+  MQTT Broker      |
| (Selección de modo,      |      |                   |      |  (Comunicación    |
| velocidad, botella)      |      +-------------------+      |   en red)         |
|                          |              |                   |                   |
+--------------------------+              |                   +-------------------+
            |                             |                            ^
            v                             v                            |
+---------------------+      +---------------------+                   |
|   Display 7 segmentos|<-----+    LED RGB PWM     |                   |
| (Visualización      |      | (Estados del sistema|                   |
| de selección/estado)|      |  con colores)       +-------------------+
+---------------------+      +---------------------+                   |
            ^                             |                            |
            |                             v                            |
+---------------------+      +---------------------+                   |
|   Sensor IR         +----->+  Detección de       |                   |
| (Detección de       |      |  botellas y         |                   |
| botellas y atascos) |      |  cálculo de         |                   |
+---------------------+      |  intervalos         |                   |
                             +---------------------+                   |
```

- **El usuario interactúa** mediante el encoder y botón para elegir modo, velocidad o tipo de botella.
- **El microcontrolador (RPi Pico W)** procesa entradas, controla el display, el LED RGB y recibe datos del sensor IR.
- **El sistema publica el estado, velocidad y modo** al broker MQTT para monitoreo remoto.

---

## 🚦 Estados del sistema

- **Funcionando:** LED verde, operación normal.
- **Atasco:** LED rojo parpadeante, requiere intervención manual (resolución desde el botón).
- **Regulando:** LED amarillo, en modo manual esperando referencia de velocidad.
- **Seleccionando/Pausa:** LED azul, mientras se eligen parámetros o el sistema está pausado.


## 👩‍💻 Colaboradores

Este proyecto está siendo desarrollado gracias al trabajo conjunto de:

- [flor-galarza](https://github.com/flor-galarza)
- [cazm0](https://github.com/cazm0)
- [IanNunez21](https://github.com/IanNunez21)
- [MaxDCoc](https://github.com/MaxDCoc)
- [Renzo Urturi](https://github.com/Renzo-14)

---

## ⚙️ Instalación y puesta en marcha

1. **Hardware:**  
   - Raspberry Pi Pico W  
   - Sensor IR  
   - Encoder rotativo + botón  
   - Display 7 segmentos  
   - LED RGB (PWM)

2. **Configuración:**  
   - Edita SSID, PASSWORD y BROKER MQTT en el código.
   - Sube el archivo correspondiente (`v3.py` o el de la rama que desees) a tu placa Pico W.

3. **Funcionamiento:**  
   - El sistema se conecta a WiFi y MQTT, y entra en modo selección.
   - Elige modo, velocidad o tipo de botella desde el encoder/botón.
   - Monitorea el paso de botellas y publica los datos por MQTT.

---

## 📝 Ejemplo de payload MQTT

```json
{
  "equipo": "CortoCircuito",
  "magnitudes": ["estado", "velocidad", "modo"]
}
```

---
