# Diagrama de Circuito

## Componentes

- ESP32 DevKit
- Sensor ultrasonico HC-SR04
- Modulo relé 5V
- LCD 16x2 con adaptador I2C
- Protoboard
- 5 botones (cruzeta + OK)
- Resistencias 10k (5 unidades)
- Cables de conexion

## Conexiones

| Componente | Pin | GPIO ESP32 |
|---|---|---|
| HC-SR04 Trig | OUT | GPIO 13 |
| HC-SR04 Echo | IN | GPIO 12 |
| Relé IN | DIGITAL | GPIO 27 |
| LCD I2C SDA | I2C | GPIO 21 |
| LCD I2C SCL | I2C | GPIO 22 |
| Boton Arriba | BUTTON | GPIO 15 |
| Boton Abajo | BUTTON | GPIO 2 |
| Boton Izquierda | BUTTON | GPIO 4 |
| Boton Derecha | BUTTON | GPIO 16 |
| Boton OK | BUTTON | GPIO 0 |
| Wake pin | INTERRUPT | GPIO 33 |

## Alimentacion

- ESP32: 5V via USB o VIN
- Relé: 5V desde ESP32 (5V pin)
- LCD I2C: 5V (VCC)
- HC-SR04: 5V (VCC)
