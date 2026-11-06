# MeuLab AirDial

[Português](#português) · [English](#english)

## Português

Firmware de radar de aeronaves para **M5Dial**. Consulta o feed público de [Radar MeuLab](https://radar.meulab.fun/) em `https://radar.meulab.fun/data/aircraft.json` a cada 15 segundos e mostra voos numa tela circular de 240 × 240 px. O encoder e o botão permitem consultar aeronaves sem celular ou computador.

### Requisitos

- M5Dial ou M5Dial v1.1 (ESP32-S3, flash de 8 MB)
- Cabo USB-C com dados
- Wi-Fi de 2,4 GHz com acesso à internet
- [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation/index.html)

### Configuração

```sh
cp include/secrets.example.h include/secrets.h
```

Edite `include/secrets.h` com o SSID e a senha da sua rede. Esse arquivo está no `.gitignore`: **não publique suas credenciais**. O firmware grava as credenciais no dispositivo durante a instalação.

### Compilar e instalar

```sh
pio run -e m5dial
pio run -e m5dial -t upload --upload-port /dev/cu.usbmodem2101
pio device monitor --port /dev/cu.usbmodem2101 --baud 115200
```

Troque a porta serial conforme seu sistema. No Linux, geralmente `/dev/ttyACM0`; no Windows, `COM3` ou similar. A primeira compilação baixa as bibliotecas declaradas em `platformio.ini`.

### Uso

Gire o dial para escolher aeronave, ordenadas por distância. Toque na tela ou pressione o botão para abrir ou fechar detalhes. Segure o botão por 1,2 segundo para atualizar. O aro indica estado do Wi-Fi/feed e o ponto no aro indica direção da aeronave em relação ao radar. Se o feed falhar, a última leitura continua visível com alerta e idade dos dados.

O feed fornece indicativo, registro, tipo, altitude, velocidade, rumo e distância quando disponíveis. Campos ausentes aparecem como traços; nem toda aeronave transmite todos eles. A distância `r_dst` vem em milhas náuticas. A conexão HTTPS lê dados públicos sem validar certificado; não envie credenciais ou outros dados privados para esse endpoint.

### Backup e restauração

**Faça o backup antes de gravar firmware novo.** O comando abaixo lê os 8 MB completos da flash do dispositivo conectado:

```sh
esptool --port /dev/cu.usbmodem2101 --baud 921600 read-flash 0x0 0x800000 m5dial-original.bin
shasum -a 256 m5dial-original.bin
```

Guarde o arquivo em local privado. Uma imagem completa pode conter dados de Wi-Fi e outros segredos do firmware anterior. **Não adicione o backup ao GitHub.**

Para restaurar **no mesmo dispositivo**:

```sh
esptool --port /dev/cu.usbmodem2101 --baud 921600 write-flash 0x0 m5dial-original.bin
```

A restauração substitui firmware, configuração e dados da flash. Confira tamanho de 8.388.608 bytes e hash do backup antes de executar.

### Fonte dos dados

Os dados vêm de [Radar MeuLab](https://radar.meulab.fun/data/aircraft.json), não de um receptor ADS-B embutido no M5Dial. Requer internet. O feed pode ter atrasos, dados incompletos ou indisponibilidade; não use para navegação aeronáutica.

## English

Aircraft radar firmware for **M5Dial**. It fetches the public [Radar MeuLab](https://radar.meulab.fun/) feed at `https://radar.meulab.fun/data/aircraft.json` every 15 seconds and displays flights on the 240 × 240 px round screen. The rotary encoder and button let you browse aircraft without a phone or computer.

### Requirements

- M5Dial or M5Dial v1.1 (ESP32-S3, 8 MB flash)
- Data-capable USB-C cable
- 2.4 GHz Wi-Fi with internet access
- [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation/index.html)

### Configure

```sh
cp include/secrets.example.h include/secrets.h
```

Enter your Wi-Fi SSID and password in `include/secrets.h`. This file is gitignored: **never publish your credentials**. Installing the firmware writes them to the device.

### Build and install

```sh
pio run -e m5dial
pio run -e m5dial -t upload --upload-port /dev/cu.usbmodem2101
pio device monitor --port /dev/cu.usbmodem2101 --baud 115200
```

Replace the serial port for your system. Linux commonly uses `/dev/ttyACM0`; Windows uses `COM3` or similar. The first build downloads libraries declared in `platformio.ini`.

### Use

Turn the dial to select aircraft, ordered by distance. Tap the screen or press the button to open or close details. Hold the button for 1.2 seconds to refresh. The outer ring shows Wi-Fi/feed state and its dot points toward the aircraft relative to the radar. If the feed fails, the last result stays visible with a stale warning and data age.

The feed supplies callsign, registration, type, altitude, speed, heading, and distance when available. Missing fields appear as dashes; not every aircraft broadcasts every field. `r_dst` distance is in nautical miles. HTTPS reads public data without certificate validation; do not send credentials or private data to this endpoint.

### Backup and restore

**Back up before installing new firmware.** This reads all 8 MB of flash from the connected device:

```sh
esptool --port /dev/cu.usbmodem2101 --baud 921600 read-flash 0x0 0x800000 m5dial-original.bin
shasum -a 256 m5dial-original.bin
```

Keep the image private. A full image can contain Wi-Fi credentials and other secrets from the previous firmware. **Do not add it to GitHub.**

To restore **to the same device**:

```sh
esptool --port /dev/cu.usbmodem2101 --baud 921600 write-flash 0x0 m5dial-original.bin
```

Restoring replaces firmware, settings, and flash data. Check the backup is 8,388,608 bytes and verify its hash before running the command.

### Data source

Data comes from [Radar MeuLab](https://radar.meulab.fun/data/aircraft.json), not from an ADS-B receiver inside the M5Dial. Internet access is required. The feed may be delayed, incomplete, or unavailable; do not use it for aviation navigation.
