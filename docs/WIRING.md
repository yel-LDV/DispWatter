# Conexionado del hardware

Guía de cableado del ESP32, el sensor ultrasónico, el relé y la pantalla LCD.
Los pines están definidos en `hardware/esp32/main/src/config.h` y no contienen
credenciales ni datos de usuario.

> **Seguridad primero**: si el relé conmuta 230 V, usa un módulo optoacoplado,
> separa físicamente la parte de red del circuito de baja tensión y trabaja
> siempre con la alimentación desconectada.

---

## 1. Pines usados

| Función | GPIO | Modo | Notas |
| --- | --- | --- | --- |
| HC-SR04 `TRIG` | 5 | Salida | Pulso de disparo de 10 µs |
| HC-SR04 `ECHO` | 18 | Entrada | **Requiere divisor de tensión a 3,3 V** |
| Relé `IN` | 4 | Salida | Módulo activo en LOW (`RELE_ON = LOW`) |
| LCD I2C `SDA` | 21 | I2C | Dirección por defecto `0x27` |
| LCD I2C `SCL` | 22 | I2C | 5 V en la mayoría de módulos |
| Botón de despertar | 33 | Entrada | `INPUT_PULLUP`, activo en LOW, `ext0` |
| Alimentación | — | — | 5 V para sensor, relé y LCD; 3,3 V para el ESP32 |

Evita usar GPIO 6–11 (flash), GPIO 34–39 (solo entrada) y los pines de arranque
(0, 2, 12, 15) para el relé o el botón.

---

## 2. HC-SR04 (nivel de agua)

El HC-SR04 trabaja a 5 V y su salida `ECHO` también es de 5 V. El ESP32 **no
tolera 5 V en sus GPIO**, así que usa un divisor de tensión antes del GPIO 18.

```
HC-SR04 ECHO ──[ R1 1 kΩ ]──┬── GPIO 18 (ESP32)
                            │
                        [ R2 2 kΩ ]
                            │
                           GND
```

- R1 = 1 kΩ entre `ECHO` y el nodo del GPIO.
- R2 = 2 kΩ entre el nodo del GPIO y GND.
- Tensión en el GPIO: `5 V × 2 / (1 + 2) = 3,33 V`. Es el límite aceptable;
  para mayor margen puedes usar R1 = 1 kΩ y R2 = 2,2 kΩ (≈3,1 V).
- Une **GND del HC-SR04 con GND del ESP32**.
- Alimenta el sensor a 5 V (VCC), no a 3,3 V: a 3,3 V pierde alcance.
- Monta el sensor perpendicular al fondo y deja la distancia al espejo de agua
  por debajo del máximo para que no se moje.

---

## 3. Relé / bomba

El firmware asume un módulo de relé **activo en LOW**:

- `RELE_ON = LOW` → bobina activada.
- `RELE_OFF = HIGH` → bobina desactivada.

Conexionado típico:

```
ESP32 GPIO 4 ────────────── IN del módulo relé
ESP32 GND ───────────────── GND del módulo relé
5 V (fuente) ────────────── VCC del módulo relé
```

### Pull-up obligatorio en la entrada del relé

Durante el arranque y el deep sleep, los GPIO del ESP32 quedan flotantes unos
milisegundos. Un módulo activo en LOW puede activar la bomba en ese instante.
Instala una resistencia externa de **10 kΩ entre `IN` y 3,3 V** para mantener el
relé apagado mientras el GPIO no está configurado.

```
3,3 V ──[ 10 kΩ ]──┬── GPIO 4 ── IN del relé
                    │
                 (opcional) 100 nF a GND para ruido
```

Comprueba con un polímetro que el relé permanece apagado al pulsar `RESET` y al
entrar en deep sleep.

### Contactos de potencia

- Usa `COM` y `NO` para que la bomba esté apagada sin alimentación.
- Añade un fusible adecuado en la línea de potencia.
- Para bombas de CC, instala un diodo de rueda libre (flyback) en paralelo con
  la carga.
- Para 230 V, usa cableado, borneras y aislamiento homologados; nunca alimentes
  la bomba desde el regulador del ESP32.

---

## 4. Pantalla LCD 16x2 I2C

| LCD | ESP32 |
| --- | --- |
| `GND` | `GND` |
| `VCC` | `5 V` |
| `SDA` | `GPIO 21` |
| `SCL` | `GPIO 22` |

- Dirección I2C por defecto: `0x27`. Si tu módulo usa `0x3F`, cámbiala en
  `LCD_I2C_ADDR` de `config.h`.
- Si la pantalla muestra caracteres basura, ajusta el contraste con el
  potenciómetro del módulo I2C.
- El firmware muestra el estado de configuración, WiFi, backend, distancia y
  relé. Los comandos `display` del panel tienen prioridad durante 10 s.

---

## 5. Botón de despertar (deep sleep)

```
GPIO 33 ──┬── pulsador ── GND
          │
        (interno) pull-up
```

- El firmware configura `INPUT_PULLUP` y `esp_sleep_enable_ext0_wakeup` con
  nivel LOW.
- Puedes añadir un condensador de 100 nF entre GPIO 33 y GND para antirrebote.
- No uses GPIO 34–39 para el botón: no tienen pull-up interno.
- El otro mecanismo de despertar es el temporizador configurado en
  `power.sleep_timer_min` o el que envíe el panel con la acción `sleep`.

> Un dispositivo en deep sleep **no escucha la red**. Solo despierta por
> temporizador o por el botón físico. El panel lo avisa al usar «Apagar todo».

---

## 6. Alimentación

- Fuente de 5 V / ≥2 A para ESP32 + relé + LCD + sensor.
- Condensador de 470–1000 µF en la entrada de 5 V y 100 nF junto al ESP32.
- GND común entre ESP32, sensor, relé y LCD.
- Si alimentas el ESP32 por USB durante el desarrollo, no conectes a la vez la
  salida de 5 V de la fuente al pin `5V` del ESP32.
- Separa el cableado de potencia del de señal y usa cables cortos para el
  sensor.

---

## 7. Lista de comprobación antes de encender

- [ ] Divisor de tensión instalado en `ECHO` (máximo 3,3 V en GPIO 18).
- [ ] Pull-up de 10 kΩ en `IN` del relé.
- [ ] GND común entre todos los módulos.
- [ ] Relé apagado al resetear y al entrar en deep sleep.
- [ ] Bomba conectada a `COM`/`NO` con fusible y flyback.
- [ ] LCD muestra «DispWatter / Iniciando...».
- [ ] Sin credenciales escritas en `config.h` ni en el código.
