# Guia de Actualizaciones OTA

## Como funciona

1. GitHub Actions compila el firmware automaticamente al hacer push
2. El binario se publica en GitHub Releases
3. El backend descarga el binario y lo envia al ESP32 via WebSocket
4. El ESP32 muestra "OTA lista - Presiona OK" en el LCD
5. Presiona el boton OK para confirmar y reiniciar

## Versiones disponibles

- **Estable**: Ramas main y stable, probadas y verificadas
- **Experimental**: Ramas develop y feature/*, en desarrollo
- **Insegura**: Builds de forks no verificados

## Desde el panel

1. Navega a la seccion OTA
2. Selecciona una version
3. Presiona "Actualizar"
4. Espera a que el ESP32 muestre "OTA lista"
5. Presiona OK en el dispositivo

## Desde los botones

- Mantener OK + Arriba por 2 segundos activa el modo OTA
- Mantener OK + Abajo por 2 segundos activa el modo downgrade
- OK + Izquierda vuelve al modo normal
