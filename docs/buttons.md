# Guia de Navegacion por Botones

## Configuracion de botones

| Boton | GPIO | Funcion |
|---|---|---|
| Arriba | GPIO 15 | Navegar arriba |
| Abajo | GPIO 2 | Navegar abajo |
| Izquierda | GPIO 4 | Pagina anterior |
| Derecha | GPIO 16 | Pagina siguiente |
| OK | GPIO 0 | Seleccionar/Confirmar |

## Modos

### Modo Normal
- Navegacion por paginas del LCD
- Muestra informacion del dispositivo

### Modo OTA (OK + Arriba, 2 segundos)
- Lista versiones disponibles
- Botones laterales cambian de pagina
- OK selecciona version

### Modo Downgrade (OK + Abajo, 2 segundos)
- Lista versiones anteriores
- Mismo funcionamiento que modo OTA

### Volver al modo normal
- OK + Izquierda

## Confirmacion de OTA

Cuando el LCD muestra "OTA lista - Presiona OK":
1. Presiona el boton OK
2. El ESP32 reinicia con el nuevo firmware
3. Si no presionas en 10 segundos, la OTA se cancela
