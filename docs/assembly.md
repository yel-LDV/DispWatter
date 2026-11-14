# Guia de Montaje

## Paso 1: Preparar la protoboard

Coloca la protoboard en una superficie estable. Organiza los componentes por tipo.

## Paso 2: Conectar el LCD I2C

1. Conecta VCC del LCD a la linea roja (+5V) de la protoboard
2. Conecta GND del LCD a la linea azul (GND)
3. Conecta SDA a GPIO 21 del ESP32
4. Conecta SCL a GPIO 22 del ESP32

## Paso 3: Conectar el sensor HC-SR04

1. VCC a +5V
2. GND a GND
3. Trig a GPIO 13
4. Echo a GPIO 12

## Paso 4: Conectar el modulo relé

1. VCC a +5V
2. GND a GND
3. IN a GPIO 27

## Paso 5: Conectar los botones

Cada boton conecta entre su GPIO y GND con pull-up interno activado en el firmware.

## Paso 6: Configurar el firmware

1. Crea `data/config.json` con las credenciales WiFi y del backend
2. Flasha el firmware con `pio run --upload`
