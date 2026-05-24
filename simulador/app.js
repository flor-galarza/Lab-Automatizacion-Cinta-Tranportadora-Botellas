// app.js — Lógica de simulación del firmware embebido y el escenario físico

document.addEventListener('DOMContentLoaded', () => {
    // ==========================================
    // ESTADOS Y VARIABLES DEL FIRMWARE
    // ==========================================
    const modes = [1, 2]; // 1 = Manual, 2 = Automático
    let modeIndex = 0;
    
    const velocities = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
    let velIndex = 4; // Inicializa en 0.5 m/s (velocidad intermedia)
    
    const bottleTypes = [1, 2, 3, 4, 5];
    const bottleSpeeds = { 1: 0.2, 2: 0.4, 3: 0.6, 4: 0.8, 5: 0.9 };
    const bottleSizes = { 1: 0.05, 2: 0.08, 3: 0.06, 4: 0.1, 5: 0.07 };
    let bottleIndex = 0;
    
    // Intervalos esperados en modo automático (1->1s, 2->2s, 3->3s...)
    const BOTTLE_EXPECTED_INTERVAL_S = { 1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0, 5: 5.0 };
    
    // Umbrales y tolerancias
    const EXPECTED_BOTTLE_INTERVAL_S = 2.0;
    const INTERVAL_TOLERANCE_S = 1.0;
    const AUTO_INTERVAL_TOLERANCE_S = 1.0;
    const SENSOR_STALL_TIMEOUT_S = 10.0; // Reducido de 30s a 10s en simulación para testing ágil
    const NO_BOTTLE_TIMEOUT_EXTRA_S = 5.0; // 5s sobre el intervalo regular
    
    // Variables lógicas del sistema
    let selectedMode = false;
    let paused = false;
    let errorState = false;
    let encoderPressCount = 0;
    let configState = null;
    
    // Estado de tiempos del sensor IR
    let lastIrLevel = false;
    let lastStateChangeTime = null;
    let lastBottleTime = null;
    
    // Variables modo manual
    let firstManualDetection = null;
    let referenceTime = null;
    let t2 = null;
    
    // Variables modo automático
    let autoArmed = false;
    let autoFirstDetection = null;
    let lastDetection = null;
    
    // ==========================================
    // VARIABLES DE SIMULACIÓN FÍSICA
    // ==========================================
    let bottles = []; // Array de botellas en movimiento
    let bottleSpawnInterval = null;
    let physicsInterval = null;
    let simulationActive = true;
    let currentInjectedFault = 'normal'; // normal, stall, no-bottles, slow-bottles
    let nextBottleDelay = 0; // Para alterar tiempos en inyección de fallas
    let obstacleActive = false; // Sensor obstruido manualmente (stall)

    // ==========================================
    // ELEMENTOS DEL DOM
    // ==========================================
    // UI General
    const systemStatusDot = document.getElementById('system-status-dot');
    const systemStatusText = document.getElementById('system-status-text');
    const simSpeedVal = document.getElementById('sim-speed-val');
    
    // Hardware Embebido
    const ledRGB = document.getElementById('led-rgb-physical');
    const encoderKnob = document.getElementById('encoder-knob');
    const encoderLeftBtn = document.getElementById('encoder-left-btn');
    const encoderRightBtn = document.getElementById('encoder-right-btn');
    const encoderSwBtn = document.getElementById('encoder-sw-btn');
    const sensorIrVisual = document.getElementById('sensor-ir-visual');
    const sensorIrLed = document.getElementById('sensor-ir-led');
    const sensorIrStatusText = document.getElementById('sensor-ir-status');
    const lastIntervalText = document.getElementById('last-interval-text');
    const bottleCurrentIcon = document.getElementById('bottle-current-status-icon');
    
    // Cinta Transportadora
    const conveyorTrack = document.getElementById('conveyor-track');
    const irBeam = document.getElementById('ir-beam');
    const rollers = document.querySelectorAll('.roller');
    
    // MQTT
    const mqttEstado = document.getElementById('mqtt-val-estado');
    const mqttVelocidad = document.getElementById('mqtt-val-velocidad');
    const mqttModo = document.getElementById('mqtt-val-modo');
    const discoveryEquipo = document.getElementById('discovery-equipo');
    const discoveryMags = document.getElementById('discovery-mags');
    
    // Terminal
    const serialOutput = document.getElementById('serial-output');
    const btnClearTerminal = document.getElementById('btn-clear-terminal');
    
    // Inyección de Fallas
    const btnNormalFlow = document.getElementById('btn-normal-flow');
    const btnStallSensor = document.getElementById('btn-stall-sensor');
    const btnNoBottles = document.getElementById('btn-no-bottles');
    const btnSlowBottles = document.getElementById('btn-slow-bottles');

    // ==========================================
    // DIBUJAR DISPLAY 7 SEGMENTOS
    // ==========================================
    const digitPatterns = {
        0: ['seg-a', 'seg-b', 'seg-c', 'seg-d', 'seg-e', 'seg-f'],
        1: ['seg-b', 'seg-c'],
        2: ['seg-a', 'seg-b', 'seg-d', 'seg-e', 'seg-g'],
        3: ['seg-a', 'seg-b', 'seg-c', 'seg-d', 'seg-g'],
        4: ['seg-b', 'seg-c', 'seg-f', 'seg-g'],
        5: ['seg-a', 'seg-c', 'seg-d', 'seg-f', 'seg-g'],
        6: ['seg-a', 'seg-c', 'seg-d', 'seg-e', 'seg-f', 'seg-g'],
        7: ['seg-a', 'seg-b', 'seg-c'],
        8: ['seg-a', 'seg-b', 'seg-c', 'seg-d', 'seg-e', 'seg-f', 'seg-g'],
        9: ['seg-a', 'seg-b', 'seg-c', 'seg-d', 'seg-f', 'seg-g'],
        'E': ['seg-a', 'seg-d', 'seg-e', 'seg-f', 'seg-g'], // Error
        'OFF': []
    };

    function displayDigit(digit) {
        // Apagar todos primero
        const allSegments = document.querySelectorAll('.segment');
        allSegments.forEach(seg => seg.classList.remove('active'));
        
        // Activar los correspondientes
        const pattern = digitPatterns[digit];
        if (pattern) {
            pattern.forEach(segId => {
                const seg = document.getElementById(segId);
                if (seg) seg.classList.add('active');
            });
        }
    }

    // ==========================================
    // CONTROL DEL LED RGB
    // ==========================================
    function setLED(color) {
        ledRGB.className = 'led-rgb'; // Reset
        if (color) ledRGB.classList.add(color);
    }

    // ==========================================
    // LOGS DE CONSOLA / TERMINAL SERIAL
    // ==========================================
    function printTerminal(text, type = 'normal') {
        const time = new Date();
        const stamp = `${time.getHours().toString().padStart(2, '0')}:${time.getMinutes().toString().padStart(2, '0')}:${time.getSeconds().toString().padStart(2, '0')}.${(time.getMilliseconds() / 10).toFixed(0).padStart(2, '0')}`;
        
        const line = document.createElement('div');
        line.className = 'log-line';
        
        let textClass = 'log-text';
        if (type === 'success') textClass = 'log-normal';
        else if (type === 'info') textClass = 'log-info';
        else if (type === 'warning') textClass = 'log-warning';
        else if (type === 'error') textClass = 'log-error';
        else if (type === 'serial') textClass = 'log-serial';
        
        line.innerHTML = `<span class="log-time">[${stamp}]</span><span class="${textClass}">${text}</span>`;
        serialOutput.appendChild(line);
        serialOutput.scrollTop = serialOutput.scrollHeight;
    }

    btnClearTerminal.addEventListener('click', () => {
        serialOutput.innerHTML = '';
        printTerminal('Consola serial limpiada.', 'info');
    });

    // ==========================================
    // TELEMETRÍA MQTT SIMULADA
    // ==========================================
    function computeState() {
        if (errorState) return "Atasco";
        if (paused || !selectedMode) return "Seleccionando";
        if (modes[modeIndex] === 1) {
            if (firstManualDetection === null || referenceTime === null) {
                return "Regulando";
            }
            return "Funcionando";
        }
        return "Funcionando";
    }

    function publishMQTT() {
        const estado = computeState();
        let velocidad = 0.0;
        let modo = modes[modeIndex] === 1; // true = Manual, false = Automático
        
        if (!errorState) {
            if (modes[modeIndex] === 1) {
                velocidad = velocities[velIndex];
            } else {
                const bt = bottleTypes[bottleIndex];
                velocidad = bottleSpeeds[bt];
            }
        }
        
        // Simular publicación al Broker
        mqttEstado.textContent = estado;
        mqttVelocidad.textContent = `${velocidad.toFixed(2)} m/s`;
        mqttModo.textContent = modo ? "manual" : "automático";
        
        // Actualizar Discovery
        discoveryEquipo.textContent = "CortoCircuito";
        discoveryMags.textContent = "estado, velocidad, modo";
        
        // Colores según estado en MQTT boxes
        if (estado === "Atasco") {
            mqttEstado.style.color = 'var(--color-error)';
            mqttVelocidad.style.color = 'var(--color-error)';
        } else if (estado === "Seleccionando") {
            mqttEstado.style.color = 'var(--color-selecting)';
            mqttVelocidad.style.color = 'var(--color-selecting)';
        } else if (estado === "Regulando") {
            mqttEstado.style.color = 'var(--color-yellow)';
            mqttVelocidad.style.color = 'var(--color-yellow)';
        } else {
            mqttEstado.style.color = 'var(--color-normal)';
            mqttVelocidad.style.color = 'var(--color-normal)';
        }
    }

    // Publicar velocidad serial cada vez que cambia (como el print() del código)
    function publishSerialVelocity() {
        let velocidadSerial = 0.0;
        if (!errorState) {
            if (modes[modeIndex] === 1) {
                velocidadSerial = velocities[velIndex];
            } else {
                const bt = bottleTypes[bottleIndex];
                velocidadSerial = bottleSpeeds[bt];
            }
        }
        printTerminal(`VELOCIDAD:${velocidadSerial.toFixed(2)}`, 'serial');
    }

    // ==========================================
    // LOGICA DE LA PLACA Y COMPONENTES
    // ==========================================
    let encoderRotation = 0;
    
    function rotateEncoderVisual(direction) {
        encoderRotation += direction * 30; // 30 grados por paso
        encoderKnob.style.transform = `rotate(${encoderRotation}deg)`;
    }

    function now_s() {
        return Date.now() / 1000;
    }

    // Actualiza la interfaz del badge general
    function updateSystemBadge() {
        const estado = computeState();
        systemStatusText.textContent = estado.toUpperCase();
        
        systemStatusDot.className = 'status-indicator-dot';
        if (estado === 'Atasco') {
            systemStatusDot.classList.add('error');
            systemStatusDot.style.backgroundColor = 'var(--color-error)';
            systemStatusDot.style.boxShadow = 'var(--glow-error)';
        } else if (estado === 'Seleccionando') {
            systemStatusDot.classList.add('selecting');
            systemStatusDot.style.backgroundColor = 'var(--color-selecting)';
            systemStatusDot.style.boxShadow = 'var(--glow-selecting)';
        } else if (estado === 'Regulando') {
            systemStatusDot.classList.add('yellow');
            systemStatusDot.style.backgroundColor = 'var(--color-yellow)';
            systemStatusDot.style.boxShadow = 'var(--glow-yellow)';
        } else {
            systemStatusDot.classList.add('normal');
            systemStatusDot.style.backgroundColor = 'var(--color-normal)';
            systemStatusDot.style.boxShadow = 'var(--glow-normal)';
        }
    }

    // ==========================================
    // PROGRAMA PRINCIPAL (MÁQUINA DE ESTADOS)
    // ==========================================
    
    // Inicializar Programa
    function setup() {
        printTerminal('Iniciando CircuitPython en Raspberry Pi Pico 2W...', 'info');
        printTerminal('SSID local: "wfrre-Docentes". Conectando a la red...', 'info');
        setTimeout(() => {
            printTerminal('Conectado a wfrre-Docentes. IP: 10.13.100.124', 'success');
            printTerminal('Conectando a Broker MQTT (10.13.100.72)...', 'info');
            setTimeout(() => {
                printTerminal('Conectado al broker MQTT exitosamente.', 'success');
                printTerminal('Descubrimiento publicado en broker.', 'success');
                
                // Entrar al menú de selección de modo
                printTerminal('--- MENÚ SELECCIÓN DE MODO ---', 'info');
                printTerminal('Gira el encoder para elegir Modo: 1=Manual, 2=Automático', 'info');
                updateHardwareOutputs();
                startPhysicalSimulation();
                
                // Spawnear botellas iniciales de muestra
                spawnBottle();
                bottles[0].x = 20;
                bottles[0].element.style.left = '20%';
                
                spawnBottle();
                bottles[1].x = 50;
                bottles[1].element.style.left = '50%';
            }, 800);
        }, 800);
    }

    // Actualizar LED y Display 7 Segmentos según estado global de la máquina
    function updateHardwareOutputs() {
        updateSystemBadge();
        
        if (errorState) {
            displayDigit('E');
            setLED('error');
            return;
        }
        
        if (paused) {
            setLED('selecting');
            displayDigit(modes[modeIndex] === 1 ? velIndex + 1 : bottleTypes[bottleIndex]);
            return;
        }
        
        if (!selectedMode) {
            // En selección inicial
            displayDigit(modes[modeIndex]);
            setLED('selecting');
        } else {
            // Corriendo normal
            if (modes[modeIndex] === 1) {
                // Modo Manual
                if (firstManualDetection === null || referenceTime === null) {
                    setLED('yellow'); // Regulando
                } else {
                    setLED('normal'); // Funcionando
                }
                displayDigit(velIndex + 1);
            } else {
                // Modo Automático
                setLED('normal'); // Funcionando
                displayDigit(bottleTypes[bottleIndex]);
            }
        }
        publishMQTT();
    }

    // Manejar el botón del encoder (SW)
    function handleEncoderClick() {
        if (errorState) {
            // Acknowledge de error: 3 presiones para reiniciar
            encoderPressCount++;
            printTerminal(`Botón presionado en estado de error (${encoderPressCount}/3)`, 'warning');
            
            if (encoderPressCount >= 3) {
                errorState = false;
                encoderPressCount = 0;
                
                // Reinicios lógicos
                firstManualDetection = null;
                referenceTime = null;
                t2 = null;
                lastStateChangeTime = now_s();
                autoArmed = (modes[modeIndex] === 2);
                autoFirstDetection = null;
                lastDetection = null;
                
                if (modes[modeIndex] === 2) {
                    lastBottleTime = now_s();
                    autoFirstDetection = now_s();
                } else {
                    lastBottleTime = null;
                }
                
                printTerminal('Error resuelto, sistema reanudado por el operario.', 'success');
                // Eliminar botellas atascadas para limpiar la cinta
                bottles = [];
                const bDOMs = document.querySelectorAll('.bottle');
                bDOMs.forEach(b => b.remove());
                
                // Volver a simulación normal
                setNormalFlowFault();
                updateHardwareOutputs();
                publishSerialVelocity();
            }
            return;
        }
        
        if (!selectedMode) {
            // Confirmación inicial de Modo
            selectedMode = true;
            printTerminal(`Modo seleccionado: ${modes[modeIndex] === 1 ? "Manual" : "Automático"}`, 'success');
            publishSerialVelocity();
            
            setTimeout(() => {
                if (modes[modeIndex] === 1) {
                    printTerminal('--- CONFIGURAR VELOCIDAD ---', 'info');
                    printTerminal('Gira el encoder para elegir Velocidad (1 a 9)', 'info');
                    // Forzar re-entrada a submenú de velocidad
                    selectedMode = false; 
                    // Usamos una variable auxiliar para saber en qué parte de la config estamos
                    configState = 'velocity';
                } else {
                    printTerminal('--- CONFIGURAR TIPO BOTELLA ---', 'info');
                    printTerminal('Gira el encoder para elegir Botella (1 a 5)', 'info');
                    selectedMode = false;
                    configState = 'bottle';
                }
                updateHardwareOutputs();
            }, 300);
            return;
        }

        // Si estamos en config secundaria
        if (typeof configState !== 'undefined' && configState !== null) {
            if (configState === 'velocity') {
                configState = null;
                selectedMode = true;
                printTerminal(`Velocidad seleccionada: ${velocities[velIndex]} m/s`, 'success');
                publishSerialVelocity();
                
                // Iniciar medición manual
                lastStateChangeTime = now_s();
                printTerminal('Sistema en marcha (Modo Manual). Pase las primeras dos botellas para calcular referencia de tiempo.', 'warning');
            } else if (configState === 'bottle') {
                configState = null;
                selectedMode = true;
                const bt = bottleTypes[bottleIndex];
                printTerminal(`Botella seleccionada: ${bt}, velocidad: ${bottleSpeeds[bt]} m/s`, 'success');
                publishSerialVelocity();
                
                // Armar conteo automático
                autoArmed = true;
                autoFirstDetection = null;
                lastDetection = null;
                lastBottleTime = now_s();
                lastStateChangeTime = lastBottleTime;
                autoFirstDetection = now_s(); // Activa timeout
                
                printTerminal(`Sistema en marcha (Modo Automático). Intervalo esperado por botella: ${BOTTLE_EXPECTED_INTERVAL_S[bt]}s`, 'success');
            }
            updateHardwareOutputs();
            return;
        }
        
        // Funcionamiento normal: Botón sirve para pausar / reanudar
        paused = !paused;
        if (paused) {
            printTerminal('Sistema PAUSADO. Gira el encoder para cambiar modo o parámetros.', 'warning');
        } else {
            // Reanudar e iniciar resets según el modo
            if (modes[modeIndex] === 1) {
                firstManualDetection = null;
                referenceTime = null;
                t2 = null;
                lastBottleTime = null;
                lastStateChangeTime = now_s();
                autoArmed = false;
                autoFirstDetection = null;
                printTerminal('Sistema reanudado en Manual (se requiere nueva calibración de intervalo).', 'info');
            } else {
                lastBottleTime = now_s();
                lastStateChangeTime = now_s();
                autoArmed = true;
                autoFirstDetection = now_s();
                printTerminal('Sistema reanudado en Automático.', 'info');
            }
        }
        updateHardwareOutputs();
    }

    // Girar el encoder hacia izquierda (-1) o derecha (1)
    function handleEncoderRotate(direction) {
        rotateEncoderVisual(direction);
        
        // 1. Selección inicial de modo
        if (!selectedMode && (typeof configState === 'undefined' || configState === null)) {
            modeIndex = (modeIndex + direction + modes.length) % modes.length;
            printTerminal(`Encoder girado. Modo enfocado: ${modes[modeIndex] === 1 ? '1 (Manual)' : '2 (Automático)'}`, 'info');
            updateHardwareOutputs();
            return;
        }
        
        // 2. Selección de velocidad en manual
        if (!selectedMode && typeof configState !== 'undefined' && configState === 'velocity') {
            velIndex = Math.max(0, Math.min(velocities.length - 1, velIndex + direction));
            printTerminal(`Encoder girado. Velocidad enfocada: ${velocities[velIndex]} m/s`, 'info');
            updateHardwareOutputs();
            return;
        }
        
        // 3. Selección de botella en automático
        if (!selectedMode && typeof configState !== 'undefined' && configState === 'bottle') {
            bottleIndex = (bottleIndex + direction + bottleTypes.length) % bottleTypes.length;
            const bt = bottleTypes[bottleIndex];
            printTerminal(`Encoder girado. Botella enfocada: Tipo ${bt} (Velocidad: ${bottleSpeeds[bt]} m/s, Intervalo: ${BOTTLE_EXPECTED_INTERVAL_S[bt]}s)`, 'info');
            updateHardwareOutputs();
            return;
        }
        
        // 4. Si está pausado, permite volver a configurar modo y variables
        if (paused) {
            selectedMode = false;
            configState = null;
            modeIndex = (modeIndex + direction + modes.length) % modes.length;
            printTerminal(`Reconfigurando. Modo enfocado: ${modes[modeIndex] === 1 ? '1 (Manual)' : '2 (Automático)'}`, 'info');
            updateHardwareOutputs();
        }
    }

    // Event listeners del encoder físico simulado
    encoderLeftBtn.addEventListener('click', () => handleEncoderRotate(-1));
    encoderRightBtn.addEventListener('click', () => handleEncoderRotate(1));
    encoderSwBtn.addEventListener('click', handleEncoderClick);
    
    // Permitir click en el pomo del encoder
    encoderKnob.addEventListener('click', handleEncoderClick);

    // ==========================================
    // DETECCIÓN DE ATASCOS (CÓDIGO EQUIVALENTE PICO)
    // ==========================================
    function triggerJam(reasonText) {
        if (errorState) return;
        errorState = true;
        encoderPressCount = 0;
        printTerminal(`¡ATASCO DETECTADO! Razón: ${reasonText}`, 'error');
        printTerminal('Forzando velocidad a 0.00 m/s por atasco.', 'error');
        
        // Reporte plotter serial
        printTerminal('VELOCIDAD:0.00', 'serial');
        
        updateHardwareOutputs();
    }

    // Lógica periódica equivalente al loop principal del Pico para evaluar atascos
    function checkJamLogic() {
        if (errorState || paused || !selectedMode || (typeof configState !== 'undefined' && configState !== null)) {
            return;
        }
        
        const t_now_loop = now_s();
        
        // A. TIMEOUT POR SENSOR STALL (Sin cambios mucho tiempo)
        if (lastStateChangeTime !== null && lastBottleTime !== null) {
            const timeSinceLastStateChange = t_now_loop - lastStateChangeTime;
            if (timeSinceLastStateChange > SENSOR_STALL_TIMEOUT_S) {
                triggerJam(`Sensor atascado (Stall) sin cambios de nivel por > ${SENSOR_STALL_TIMEOUT_S.toFixed(1)}s`);
                return;
            }
        }
        
        // B. LÓGICA MODO MANUAL
        if (modes[modeIndex] === 1) {
            // Si ya reguló y está en marcha
            if (firstManualDetection !== null && referenceTime !== null && lastBottleTime !== null) {
                const timeSinceLastBottle = t_now_loop - lastBottleTime;
                const expectedInterval = referenceTime;
                
                // Timeout por no llegada de botellas
                if (timeSinceLastBottle > (expectedInterval + INTERVAL_TOLERANCE_S + NO_BOTTLE_TIMEOUT_EXTRA_S)) {
                    triggerJam(`No se detectan botellas a tiempo en Manual (límite superado: > ${(expectedInterval + INTERVAL_TOLERANCE_S + NO_BOTTLE_TIMEOUT_EXTRA_S).toFixed(2)}s)`);
                }
            }
        } 
        // C. LÓGICA MODO AUTOMÁTICO
        else {
            const bt = bottleTypes[bottleIndex];
            const expectedInterval = BOTTLE_EXPECTED_INTERVAL_S[bt];
            
            // Timeout por no llegada de botellas en automático
            if (autoFirstDetection !== null && lastBottleTime !== null) {
                const timeSinceLastBottle = t_now_loop - lastBottleTime;
                if (timeSinceLastBottle > (expectedInterval + AUTO_INTERVAL_TOLERANCE_S + NO_BOTTLE_TIMEOUT_EXTRA_S)) {
                    triggerJam(`No se detectan botellas a tiempo en Automático (límite superado: > ${(expectedInterval + AUTO_INTERVAL_TOLERANCE_S + NO_BOTTLE_TIMEOUT_EXTRA_S).toFixed(2)}s)`);
                }
            }
        }
    }

    // Procesar flanco de subida (cuando entra botella al sensor IR)
    function onSensorEdgeRise() {
        if (errorState || paused || !selectedMode || (typeof configState !== 'undefined' && configState !== null)) {
            return;
        }
        
        const t = now_s();
        printTerminal('Flanco de subida en Sensor IR (Botella entra en zona)', 'info');
        
        // Feedback visual
        bottleCurrentIcon.classList.add('active');
        setTimeout(() => bottleCurrentIcon.classList.remove('active'), 500);

        // LÓGICA MANUAL
        if (modes[modeIndex] === 1) {
            if (firstManualDetection === null) {
                firstManualDetection = t;
                lastBottleTime = t;
                printTerminal(`Primera botella detectada en t=${firstManualDetection.toFixed(2)}s (Calibrando...)`, 'warning');
                updateHardwareOutputs();
            } 
            else if (referenceTime === null) {
                referenceTime = t - firstManualDetection;
                printTerminal(`Segunda botella detectada en t=${t.toFixed(2)}s → Intervalo calibrado = ${referenceTime.toFixed(2)}s`, 'success');
                lastIntervalText.textContent = `${referenceTime.toFixed(2)}s (REF)`;
                
                t2 = t;
                lastBottleTime = t;
                updateHardwareOutputs();
            } 
            else {
                printTerminal(`Botella detectada en t=${t.toFixed(2)}s`, 'info');
                
                if (t2 !== null) {
                    const elapsed = t - t2;
                    lastIntervalText.textContent = `${elapsed.toFixed(2)}s`;
                    const expectedInterval = referenceTime;
                    
                    // Comprobar atasco por intervalo incorrecto (tolerancia ±1s)
                    const diff = Math.abs(elapsed - expectedInterval);
                    printTerminal(`Evaluando intervalo: esperado=${expectedInterval.toFixed(2)}s, real=${elapsed.toFixed(2)}s, desvío=${diff.toFixed(2)}s (límite: ±${INTERVAL_TOLERANCE_S}s)`);
                    
                    if (diff > INTERVAL_TOLERANCE_S) {
                        triggerJam(`Intervalo fuera de tolerancia en Manual (esperado=${expectedInterval.toFixed(2)}s, real=${elapsed.toFixed(2)}s)`);
                        return;
                    }
                }
                t2 = t;
                lastBottleTime = t;
            }
        } 
        // LÓGICA AUTOMÁTICA
        else {
            const bt = bottleTypes[bottleIndex];
            const expectedInterval = BOTTLE_EXPECTED_INTERVAL_S[bt];
            printTerminal(`Botella detectada en t=${t.toFixed(2)}s (Auto)`, 'info');
            
            if (autoFirstDetection === null) {
                autoFirstDetection = t;
                lastBottleTime = t;
            } else {
                const elapsed = t - autoFirstDetection;
                lastIntervalText.textContent = `${elapsed.toFixed(2)}s`;
                
                // Comprobar atasco por intervalo incorrecto en automático (tolerancia ±1s)
                const diff = Math.abs(elapsed - expectedInterval);
                printTerminal(`Evaluando intervalo Auto: esperado=${expectedInterval.toFixed(2)}s, real=${elapsed.toFixed(2)}s, desvío=${diff.toFixed(2)}s (límite: ±${AUTO_INTERVAL_TOLERANCE_S}s)`);
                
                if (diff > AUTO_INTERVAL_TOLERANCE_S) {
                    triggerJam(`Intervalo fuera de tolerancia en Automático (esperado=${expectedInterval.toFixed(2)}s, real=${elapsed.toFixed(2)}s)`);
                    return;
                }
                
                autoFirstDetection = t;
                lastDetection = t;
                lastBottleTime = t;
            }
        }
    }


    // ==========================================
    // SIMULACIÓN FÍSICA Y MOTOR GRÁFICO (HTML5/JS)
    // ==========================================

    function startPhysicalSimulation() {
        let lastTime = Date.now();
        
        // Loop de física y dibujado (corre a ~60fps)
        physicsInterval = setInterval(() => {
            if (!simulationActive) return;
            
            const now = Date.now();
            const dt = (now - lastTime) / 1000;
            lastTime = now;
            
            // 1. Obtener la velocidad real
            let targetSpeed = 0;
            if (!errorState && !paused && selectedMode && (typeof configState === 'undefined' || configState === null)) {
                if (modes[modeIndex] === 1) {
                    targetSpeed = velocities[velIndex];
                } else {
                    const bt = bottleTypes[bottleIndex];
                    targetSpeed = bottleSpeeds[bt];
                }
            }
            
            // Actualizar tag de velocidad
            simSpeedVal.textContent = targetSpeed.toFixed(2);
            
            // 2. Controlar animación CSS de la cinta y rodillos
            if (targetSpeed > 0) {
                // Hacer proporcional la duración de la animación a la velocidad
                const animationDuration = 0.4 / targetSpeed; // ej: 0.5 m/s -> 0.8s
                conveyorTrack.style.animationPlayState = 'running';
                conveyorTrack.style.animationDuration = `${animationDuration}s`;
                
                rollers.forEach(roller => {
                    roller.style.animationPlayState = 'running';
                    roller.style.animationDuration = `${animationDuration}s`;
                });
            } else {
                conveyorTrack.style.animationPlayState = 'paused';
                rollers.forEach(roller => {
                    roller.style.animationPlayState = 'paused';
                });
            }
            
            // 3. Mover botellas en el DOM
            moveBottles(dt, targetSpeed);
            
            // 4. Lógica de atascos periódica (timeout)
            checkJamLogic();
        }, 16); // ~60fps
        
        // Loop de Spawn (creador) de botellas
        manageBottleSpawning();
    }

    function manageBottleSpawning() {
        if (bottleSpawnInterval) clearInterval(bottleSpawnInterval);
        
        // Revisar ritmo de spawn cada 100ms
        bottleSpawnInterval = setInterval(() => {
            if (errorState || paused || !selectedMode || (typeof configState !== 'undefined' && configState !== null)) {
                return;
            }
            
            // Si la inyección de falla retiene botellas, no creamos ninguna
            if (currentInjectedFault === 'no-bottles') {
                return;
            }
            
            // Calcular intervalo regular de creación
            let spawnInterval = 3000; // default
            if (modes[modeIndex] === 1) {
                // En manual, si ya calibró, usamos su referencia
                spawnInterval = (referenceTime ? referenceTime : EXPECTED_BOTTLE_INTERVAL_S) * 1000;
            } else {
                const bt = bottleTypes[bottleIndex];
                spawnInterval = BOTTLE_EXPECTED_INTERVAL_S[bt] * 1000;
            }
            
            // Si no hay botellas activas o la última ya avanzó suficiente, creamos una
            let canSpawn = false;
            if (bottles.length === 0) {
                canSpawn = true;
            } else {
                const lastB = bottles[bottles.length - 1];
                // Evitar colisiones: spawnear si la última avanzó al menos el 25% de la cinta
                if (lastB.x > 25) {
                    canSpawn = true;
                }
            }
            
            if (canSpawn) {
                // Verificar si tenemos un retraso inyectado (Slow / Anómalo)
                if (nextBottleDelay > 0) {
                    setTimeout(() => {
                        spawnBottle();
                        nextBottleDelay = 0;
                    }, nextBottleDelay);
                    nextBottleDelay = 0;
                } else {
                    spawnBottle();
                }
            }
        }, 300);
    }

    function spawnBottle() {
        const id = 'bottle-' + Date.now();
        const conveyorContainer = document.querySelector('.conveyor-container');
        
        // Crear elemento HTML
        const bEl = document.createElement('div');
        bEl.className = 'bottle';
        bEl.id = id;
        bEl.innerHTML = `
            <div class="bottle-neck"><div class="bottle-cap"></div></div>
            <div class="bottle-body">
                <div class="bottle-liquid"></div>
                <div class="bottle-label"></div>
            </div>
        `;
        
        conveyorContainer.appendChild(bEl);
        
        // Registrar en física (X va de 0% a 100%)
        bottles.push({
            id: id,
            element: bEl,
            x: -5, // Inicia un poco afuera de la izquierda
            sensorDetected: false
        });
    }

    function moveBottles(dt, speed) {
        // En simulación, 1 m/s equivale a recorrer ~30% de la pantalla por segundo
        const speedMultiplier = 30; 
        const movement = speed * speedMultiplier * dt;
        
        const sensorPositionX = 70; // El sensor IR está en el 70% de la cinta
        let isAnyBottleObstructing = false;
        
        // Si hay una obstrucción de falla stall inyectada, forzamos atasco de sensor
        if (obstacleActive) {
            isAnyBottleObstructing = true;
            // Buscar la botella más cercana al sensor y dejarla clavada ahí
            bottles.forEach(b => {
                if (b.x > 62 && b.x < 75) {
                    b.x = sensorPositionX; // Clavarla en el haz
                }
            });
        }
        
        for (let i = bottles.length - 1; i >= 0; i--) {
            const b = bottles[i];
            
            // Si la obstrucción está activa para esta botella específica en el sensor
            if (obstacleActive && b.x === sensorPositionX) {
                // No mover
            } else {
                b.x += movement;
            }
            
            b.element.style.left = b.x + '%';
            
            // DETECTAR CRUCE POR SENSOR IR
            // Rango de obstrucción física de la botella: cuando su cuerpo (ancho ~5%) toca el 70%
            const bottleWidthHalf = 2.5; 
            const isObstructingSensor = (b.x >= (sensorPositionX - bottleWidthHalf) && b.x <= (sensorPositionX + bottleWidthHalf));
            
            if (isObstructingSensor) {
                isAnyBottleObstructing = true;
                
                // Si es la primera vez que esta botella entra en el haz
                if (!b.sensorDetected) {
                    b.sensorDetected = true;
                    onSensorEdgeRise();
                }
            }
            
            // Eliminar botellas que salen de la cinta (> 105%)
            if (b.x > 105) {
                b.element.remove();
                bottles.splice(i, 1);
            }
        }
        
        // Actualizar el estado físico visual del sensor IR
        if (isAnyBottleObstructing) {
            if (!lastIrLevel) {
                lastIrLevel = true;
                lastStateChangeTime = now_s(); // Cambió de estado (0->1)
            }
            irBeam.classList.add('active');
            sensorIrVisual.style.borderColor = 'var(--color-error)';
            sensorIrLed.classList.add('active');
            sensorIrStatusText.textContent = "OBSTRUIDO (LOW)";
            sensorIrStatusText.style.color = 'var(--color-error)';
        } else {
            if (lastIrLevel) {
                lastIrLevel = false;
                lastStateChangeTime = now_s(); // Cambió de estado (1->0)
            }
            irBeam.classList.remove('active');
            sensorIrVisual.style.borderColor = 'rgba(255, 255, 255, 0.04)';
            sensorIrLed.classList.remove('active');
            sensorIrStatusText.textContent = "LIBRE (HIGH)";
            sensorIrStatusText.style.color = 'var(--text-secondary)';
        }
    }

    // ==========================================
    // INYECCIÓN DE FALLAS (TEST PANEL LÓGICO)
    // ==========================================
    
    function resetFaultButtons() {
        btnNormalFlow.classList.remove('active');
        btnStallSensor.classList.remove('active');
        btnNoBottles.classList.remove('active');
        btnSlowBottles.classList.remove('active');
        
        obstacleActive = false;
    }

    function ensureSystemIsRunning() {
        if (!selectedMode || paused || errorState) {
            errorState = false;
            paused = false;
            selectedMode = true;
            configState = null;
            
            // Forzar Modo Automático, Tipo Botella 2 (0.40 m/s)
            modeIndex = 1; // 2 = Automático
            bottleIndex = 1; // Botella Tipo 2
            
            autoArmed = true;
            autoFirstDetection = null;
            lastDetection = null;
            lastBottleTime = now_s();
            lastStateChangeTime = lastBottleTime;
            autoFirstDetection = now_s();
            
            // Limpiar botellas anteriores y reiniciar
            bottles = [];
            const bDOMs = document.querySelectorAll('.bottle');
            bDOMs.forEach(b => b.remove());
            
            printTerminal('Auto-Arranque: Sistema encendido en Modo Automático (Botella 2 - 0.40 m/s).', 'success');
            updateHardwareOutputs();
            publishSerialVelocity();
        }
    }

    function setNormalFlowFault() {
        ensureSystemIsRunning();
        resetFaultButtons();
        btnNormalFlow.classList.add('active');
        currentInjectedFault = 'normal';
        printTerminal('Inyección de Fallas: Flujo de cinta configurado a NORMAL.', 'success');
    }

    btnNormalFlow.addEventListener('click', setNormalFlowFault);

    btnStallSensor.addEventListener('click', () => {
        ensureSystemIsRunning();
        resetFaultButtons();
        btnStallSensor.classList.add('active');
        currentInjectedFault = 'stall';
        
        // Obstruir inmediatamente
        obstacleActive = true;
        printTerminal('Inyección de Fallas: Obstruyendo sensor IR (Stall). Simulando botella encajada.', 'warning');
    });

    btnNoBottles.addEventListener('click', () => {
        ensureSystemIsRunning();
        resetFaultButtons();
        btnNoBottles.classList.add('active');
        currentInjectedFault = 'no-bottles';
        printTerminal('Inyección de Fallas: Deteniendo alimentación de botellas. Esperando atasco por timeout...', 'warning');
    });

    btnSlowBottles.addEventListener('click', () => {
        ensureSystemIsRunning();
        resetFaultButtons();
        btnSlowBottles.classList.add('active');
        currentInjectedFault = 'slow-bottles';
        
        // Generar un retraso de 2.5 segundos adicionales en la siguiente botella
        let delayTime = 3000; // 3s adicionales
        nextBottleDelay = delayTime;
        printTerminal(`Inyección de Fallas: Alterando intervalo de paso. Retrasando botella entrante +${(delayTime/1000).toFixed(1)}s (Generará desvío de tolerancia).`, 'warning');
    });

    // Iniciar
    setNormalFlowFault();
    setup();
});
