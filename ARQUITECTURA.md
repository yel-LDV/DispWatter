# 💧 DispWatter - Documentación de Arquitectura y Especificación del Sistema

Sistema inteligente de bebedero y dispensador de agua multi-dispositivo con ESP32, comunicación bidireccional por WebSockets, backend en Python y panel de control web.

---

## 1. Visión General del Sistema

El sistema mide los niveles de agua mediante un sensor ultrasónico (HC-SR04) montado en la parte superior del contenedor. El hardware solo transmite la distancia bruta en milímetros hacia el backend. El backend centraliza la inteligencia:
1. Calcula el **porcentaje de llenado** y los **litros actuales** según la geometría calibrada del tanque.
2. Evalúa los umbrales de **riego/llenado automático**.
3. Envía órdenes al ESP32 para activar/apagar el **relé** (bomba o electroválvula) y actualizar la información de la **pantalla LCD 16x2 (I2C)**.
4. Admite **múltiples dispositivos** conectados concurrentemente.
5. Permite a los usuarios tomar posesión (*claim*) de sus dispositivos desde el panel web mediante un ID y contraseña de hardware.

```
  ┌─────────────────────────────────────────────────────────┐
  │                   ESP32 (Hardware)                      │
  │  [HC-SR04] (Medición mm) ──► [DispComm & Crypto]        │
  │  [LCD 16x2 I2C] ◄─────────── [DispComm]                 │
  │  [Relé Pin 4]   ◄─────────── [DispComm]                 │
  └────────────────────────────┬────────────────────────────┘
                               │  WebSocket Bidireccional Seguro
                               │  (JSON autenticado con SHA-256)
                               ▼
  ┌─────────────────────────────────────────────────────────┐
  │                    Backend (Python)                     │
  │  - Servidor WebSocket & Gestor de Dispositivos          │
  │  - Lógica de Tanques (Litros, Porcentajes, Histeresis)  │
  │  - Persistencia SQLite (Telemetría, Dispositivos, Users)│
  └────────────────────────────▲────────────────────────────┘
                               │  HTTP REST / WebSocket
                               ▼
  ┌─────────────────────────────────────────────────────────┐
  │                 Panel Web (Frontend)                    │
  │  - Toma de posesión de dispositivos (ID + Contraseña)   │
  │  - Configuración geométrica (Capacidad, Fondos, Espejo) │
  │  - Monitoreo en tiempo real (% y Litros) y Control Relé │
  └─────────────────────────────────────────────────────────┘
```

---

## 2. Fórmulas de Calibración de Tanque

El sensor ultrasónico se ubica en la tapa del tanque apuntando hacia el fondo:

* $D_{\text{fondo}}$: Distancia en milímetros desde el sensor hasta el fondo del tanque vacío.
* $D_{\text{espejo}}$: Distancia en milímetros desde el sensor hasta el nivel máximo del agua (espejo de agua máximo para evitar mojar el sensor).
* $D_{\text{medida}}$: Distancia leída por el sensor en milímetros.
* $V_{\text{total}}$: Capacidad nominal del contenedor en litros.

### Altura útil de agua ($H_{\text{útil}}$)
$$H_{\text{útil}} = D_{\text{fondo}} - D_{\text{espejo}}$$

### Nivel actual en milímetros ($H_{\text{actual}}$)
$$H_{\text{actual}} = D_{\text{fondo}} - D_{\text{medida}}$$

### Porcentaje de agua ($\%$)
$$\text{Porcentaje} = \text{clamp}\left( \frac{D_{\text{fondo}} - D_{\text{medida}}}{D_{\text{fondo}} - D_{\text{espejo}}} \times 100, \quad 0, \quad 100 \right)$$

### Volumen actual en litros
$$\text{Litros} = V_{\text{total}} \times \left( \frac{\text{Porcentaje}}{100} \right)$$

---

## 3. Modelo de Seguridad y Criptografía

### Identidad del Hardware
Cada ESP32 se flashea con:
* `DEVICE_ID`: Identificador único (ejemplo: `WATTER-001`).
* `DEVICE_PASS`: Clave secreta definida en el firmware (ejemplo: `watter_secret_pass_99`).
* `OWNER_ID_CLAIM`: Identificador inicial o temporal de dueño (puede ser `"UNCLAIMED"` hasta ser reclamado en el panel).

### Algoritmo de Hashing (SHA-256)
El ESP32 utiliza la aceleración por hardware de mbedTLS integrada en el ESP32 para calcular hashes SHA-256:

$$\text{DeviceKeyHash} = \text{SHA256}(\text{DEVICE\_ID} + ":" + \text{DEVICE\_PASS})$$

Durante el handshake WebSocket, el ESP32 genera un token dinámico con timestamp para evitar ataques de repetición:
$$\text{HandshakeToken} = \text{SHA256}(\text{DeviceKeyHash} + ":" + \text{timestamp})$$

### Flujo de "Toma de Posesión" (Device Claiming)
1. El usuario flashea el ESP32 con un `DEVICE_ID` y `DEVICE_PASS`.
2. El ESP32 se conecta al backend. El backend registra el dispositivo en estado `PENDING_CLAIM`.
3. El usuario inicia sesión en el panel web y va a **"Vincular Dispositivo"**.
4. Introduce el `DEVICE_ID` y `DEVICE_PASS`.
5. El backend calcula $\text{SHA256}(\text{DEVICE\_ID} + ":" + \text{DEVICE\_PASS})$ y lo compara con el hash almacenado en base de datos.
6. Si coincide, asigna el `owner_id` del usuario al dispositivo y cambia su estado a `CLAIMED`.

---

## 4. Protocolo de Mensajería Bidireccional (WebSockets JSON)

### 4.1 De ESP32 hacia Backend

#### Handshake / Autenticación:
```json
{
  "event": "auth",
  "device_id": "WATTER-001",
  "token": "a4f89b...",
  "timestamp": 1731283200
}
```

#### Telemetría Periódica:
```json
{
  "event": "telemetry",
  "device_id": "WATTER-001",
  "distance_mm": 350.5,
  "relay_state": false,
  "timestamp": 1731283210
}
```

#### Ping (Keepalive):
```json
{
  "event": "ping",
  "device_id": "WATTER-001"
}
```

---

### 4.2 De Backend hacia ESP32

#### Control de Relé (Bomba/Válvula):
```json
{
  "command": "set_relay",
  "state": true
}
```

#### Control de Pantalla LCD (I2C 16x2):
```json
{
  "command": "display",
  "line0": "Nivel: 78%  39L",
  "line1": "Bomba: ACTIVA",
  "clear": true
}
```

#### Parámetros de Muestreo:
```json
{
  "command": "config",
  "sample_interval_ms": 2000
}
```

---

## 5. Lógica del Relé (Riego / Llenado Automático)

El backend evalúa las lecturas recibidas:
1. **Llenado automático habilitado (`auto_refill == True`)**:
   * Si $\text{Porcentaje} \le \text{Nivel\_Minimo}$ $\rightarrow$ Encender relé (`state = true`), notificar al ESP32 y escribir en LCD: `"Llenando..."`.
   * Si $\text{Porcentaje} \ge \text{Nivel\_Maximo}$ $\rightarrow$ Apagar relé (`state = false`), notificar al ESP32 y escribir en LCD: `"Tanque Lleno"`.
   * **Histeresis**: Evita oscilaciones o conmutaciones rápidas cuando el agua se agita.
   * **Temporizador de seguridad**: Apaga el relé si ha estado encendido más de $N$ minutos continuos para prevenir desbordes por fallas de sensor.
2. **Control manual**: El usuario puede forzar el encendido/apagado desde el panel web, enviando inmediatamente el comando al ESP32.

---

## 6. Estructura de Software ESP32

Para mantener [`main.cpp`](file:///home/angedl_/Proyectos/DispWatter/hardware/esp32/main/src/main.cpp) minimalista y fácil de entender:

1. **[`Crypto`](file:///home/angedl_/Proyectos/DispWatter/hardware/esp32/main/Crypto)**:
   * Hasheo SHA-256 nativo con `mbedtls`.
   * Generación y verificación de tokens de autenticación.
2. **[`DispComm`](file:///home/angedl_/Proyectos/DispWatter/hardware/esp32/main/DispComm)**:
   * Conexión WiFi no bloqueante con reconexión automática.
   * Conexión WebSocket al servidor central.
   * Serialización y parseo de JSON mediante `ArduinoJson`.
   * Registro de callbacks para comandos de Relé y Pantalla LCD.
3. **[`I2C`](file:///home/angedl_/Proyectos/DispWatter/hardware/esp32/main/I2C)**:
   * Manejo directo del LCD 16x2.
4. **[`HC_SR04`](file:///home/angedl_/Proyectos/DispWatter/hardware/esp32/main/HC_SR04)**:
   * Muestreo ultrasónico con filtro de mediana en mm.
5. **[`main.cpp`](file:///home/angedl_/Proyectos/DispWatter/hardware/esp32/main/src/main.cpp)**:
   * Solo conecta los componentes con callbacks limpios.

---

## 7. Panel Web Frontend

Ubicado en [`panel/`](file:///home/angedl_/Proyectos/DispWatter/panel):
* **Gestión de Dispositivos**: Lista de bebederos vinculados, estado de conexión (Online/Offline) y botón para reclamar un nuevo bebedero con `ID` + `Contraseña`.
* **Visualización Dinámica del Tanque**: Gráfico de nivel en porcentaje animado y cálculo en litros.
* **Configuración por Dispositivo**:
  * Capacidad total (L).
  * Distancia al fondo ($D_{\text{fondo}}$ en mm).
  * Distancia al espejo máximo ($D_{\text{espejo}}$ en mm).
  * Nivel mínimo y máximo de disparo (%).
  * Interruptor de modo automático.
* **Consola de Control Manual**: Encendido manual de relé y prueba de texto en pantalla LCD.
