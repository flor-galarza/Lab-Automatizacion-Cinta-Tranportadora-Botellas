# Sistema IoT de Control y Monitoreo de Embotellado de Bebidas (Módulo "CortoCircuito")

Este proyecto implementa un sistema embebido industrial basado en **Raspberry Pi Pico 2W** y programado en **CircuitPython** para automatizar, monitorear y diagnosticar fallas en tiempo real en una línea de embotellado. El proyecto combina control de hardware embebido, algoritmos de detección defensiva de fallas, protocolos de comunicación IoT industrial (**MQTT**) y un **Simulador Web Interactivo**.

Desarrollado para la cátedra de **Tecnologías para la Automatización** de la Universidad Tecnológica Nacional - Facultad Regional Resistencia (UTN FRRE).

---

## 🚀 Características Principales

*   **Doble Lazo de Control**:
    *   **Lazo 1 (Control de Cinta)**: Control de la velocidad lineal de la cinta transportadora en dos modos de operación:
        *   *Modo Manual*: Regulación directa en pasos de `0.10 m/s` (de `0.10` a `0.90 m/s`) por medio de un encoder rotativo.
        *   *Modo Automático*: Regulación inteligente basada en el tipo de botella seleccionado (`Botella 1` a `Botella 5`) con velocidades e intervalos predefinidos.
    *   **Lazo 2 (Seguridad y Diagnóstico)**: Monitoreo de flujo continuo y detección temprana de atascos físicos utilizando un sensor de obstáculos infrarrojo.
*   **Algoritmos de Detección Defensiva de Atascos**:
    *   **Criterio de Desviación de Intervalo**: Análisis en tiempo real de la consistencia de paso de las botellas frente al intervalo esperado (con una tolerancia de `±1.0 s`). En modo Manual, el intervalo esperado se autocalibra midiendo el paso de las dos primeras botellas.
    *   **Criterio de Timeout**: Detiene la línea si no se registran pasajes de botellas durante `Intervalo + Tolerancia + 5.0 s`, asumiendo una interrupción o corte del flujo aguas arriba.
    *   **Criterio de Bloqueo de Sensor (Stall)**: Evalúa si el sensor permanece bloqueado (u obstruido) sin registrar transiciones de estado por más de `30 s`, asumiendo un atascamiento directo sobre el haz óptico.
*   **Protocolo de Comunicación IoT Industrial**:
    *   Conexión **WiFi** integrada en el microcontrolador Pico 2W.
    *   Publicación de telemetría a través del protocolo **MQTT** a un Broker centralizado (`10.13.100.72`) publicando variables en:
        *   `sensores/CortoCircuito/estado` (valores: *Funcionando*, *Atasco*, *Regulando*, *Seleccionando*).
        *   `sensores/CortoCircuito/velocidad` (velocidad en `m/s`, forzada a `0.0` en caso de atasco).
        *   `sensores/CortoCircuito/modo` (true para manual, false para automático).
    *   Descubrimiento de dispositivos automático en el canal `descubrir`.
*   **Acknowledge y Recuperación**:
    *   Mecanismo de seguridad de restauración manual ante atascos (desbloqueo controlado mediante triple pulsación en el encoder rotativo).
*   **Simulador Web Interactivo**:
    *   ¡Incluido en el repositorio! Un dashboard interactivo que simula la física de la cinta transportadora y la lógica del microcontrolador al 100% (ideal para presentación de portfolio).

---

## 🛠️ Arquitectura de Hardware y Conexiones

El hardware se encuentra cableado y modularizado en protoboard utilizando los siguientes pines de la Raspberry Pi Pico 2W:

| Componente | Tipo | Pin Pico 2W (GP) | Rol del Pin |
|---|---|---|---|
| **LED RGB KY-009** | Salida (PWM) | `GP0` (Red), `GP1` (Green), `GP2` (Blue) | Indicador visual de estado global del lazo de control |
| **Display 7 Segmentos** | Salida Digital | `GP3` a `GP9` (Segmentos A a G) | Visualizador de velocidades seleccionadas, botella y errores |
| **Encoder KY-040** | Entrada Digital | `GP10` (SW), `GP11` (DT), `GP12` (CLK) | Menú de selección interactivo, velocidad y reset de fallas |
| **Sensor IR KY-032** | Entrada Digital | `GP13` | Detector de presencia óptico de botellas (Active Low) |

---

## 🎨 Estados Visuales del Sistema (Máquina de Estados Embebida)

El sistema opera bajo una máquina de estados visual bien delimitada, reflejada en el LED RGB físico y simulado:
1.  🔵 **Azul Fijo (`Selecting`)**: Modo de navegación de menús con el encoder rotativo o estado de pausa del sistema.
2.  🟡 **Amarillo Fijo (`Regulando`)**: Modo Manual en espera de calibración (esperando que pasen las 2 primeras botellas por el sensor para calcular el intervalo regular).
3.  🟢 **Verde Fijo (`Normal`)**: Funcionamiento normal de la línea de producción. Cero errores detectados.
4.  🔴 **Rojo Parpadeante (`Error`)**: Línea de producción detenida por atasco detectado bajo cualquiera de los tres algoritmos. Requiere 3 clics en el pulsador del encoder para reiniciar.

---

## 💻 Simulador Web Interactivo (Portfolio Premium)

Para evaluar y presentar el proyecto sin necesidad de conectar el hardware físico, hemos desarrollado un **Simulador Web 100% interactivo** de calidad premium. Este se encuentra dentro de la carpeta `simulador/`.

### Características del Simulador:
1.  **Cinta 2D Animada**: Las botellas se mueven físicamente en la pantalla con una velocidad de rodillos proporcional a la velocidad configurada.
2.  **Mockup del Hardware**: Representa visualmente la placa Pico 2W con los pines correspondientes, un **Display de 7 Segmentos digital** real, un **LED RGB interactivo** y un **Encoder Rotativo** que se puede girar y pulsar.
3.  **Inyector de Fallas**: Permite simular fallas reales para probar la robustez del código de CircuitPython:
    *   *Obstrucción de Sensor (Stall)*: Bloquea una botella frente al haz IR.
    *   *Retención de Botellas (Timeout)*: Detiene la entrada de botellas a la cinta.
    *   *Intervalo Anómalo (Atasco)*: Descalibra los ritmos de llegada para simular un desfase.
4.  **Consola Serial en Tiempo Real**: Muestra exactamente las impresiones del puerto de depuración (baud 115200) que el Pico generaría, y la conexión al Broker MQTT.

### Cómo ejecutar el simulador:
1. Navega a la carpeta `/simulador`.
2. Abre el archivo [index.html](file:///d:/Flor/Documents/A%20UTN%20ISI-4/Tecnologias%20para%20la%20automatizacion/Lab1/Codigo/Lab-Automatizacion-Cinta-Tranportadora-Botellas/simulador/index.html) en tu navegador preferido. ¡Listo! Ya puedes interactuar y ver la lógica industrial en acción.

---

## 👥 Desarrolladores (Grupo "CortoCircuito")

*   **Cocito**, Maximiliano Hernán
*   **Galarza Maumary**, Florencia
*   **Nuñez**, Ian Lautaro
*   **Urturi**, Renzo Octavio
*   **Zeniquel Martinelli**, Camila Aylen
