# MeuLab AirDial

[Português](#português) · [English](#english)

## Português

Firmware de radar de aeronaves para **M5Dial**. Consulta o feed público de [Radar MeuLab](https://radar.meulab.fun/) em `https://radar.meulab.fun/data/aircraft.json` a cada 15 segundos e mostra voos sobre mapa escuro de Franca/SIMK numa tela circular de 240 × 240 px. O encoder e o botão permitem consultar aeronaves sem celular ou computador.

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

Se o upload não conectar, desligue USB, segure **G0** no módulo StampS3 atrás do Dial, reconecte USB e solte G0. A tela fica apagada no modo de gravação. Após upload, desligue e reconecte USB **sem** segurar G0 para iniciar o aplicativo. [Guia M5Stack](https://docs.m5stack.com/en/core/Dial).

### Uso

Gire o dial para escolher aeronave, ordenadas por distância. Toque na tela ou pressione o botão para abrir ou fechar detalhes. Segure o botão por 1,2 segundo para atualizar. O aro indica estado do Wi-Fi/feed; o marcador coral mostra a aeronave selecionada no mapa. Se o feed falhar, a última leitura continua visível com alerta e idade dos dados.

Mapa principal: vias reais de Franca em azul, anéis de alcance até **160 NM**, aeronaves ciano e aeronave selecionada coral. Os símbolos usam `r_dst`, `r_dir` e `track` do feed. O mapa geográfico é embarcado no firmware; funciona sem baixar tiles no M5Dial. Dados cartográficos: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL. `assets/map_franca.png` e `include/map_franca.h` são gerados por `tools/build_map.py` a partir de uma extração Overpass JSON.

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

Aircraft radar firmware for **M5Dial**. It fetches the public [Radar MeuLab](https://radar.meulab.fun/) feed at `https://radar.meulab.fun/data/aircraft.json` every 15 seconds and displays flights over a dark Franca/SIMK map on the 240 × 240 px round screen. The rotary encoder and button let you browse aircraft without a phone or computer.

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

If upload cannot connect, unplug USB, hold **G0** on the StampS3 module behind the Dial, reconnect USB, then release G0. The screen stays blank in download mode. After upload, unplug and reconnect USB **without** holding G0 to start the app. [M5Stack guide](https://docs.m5stack.com/en/core/Dial).

### Use

Turn the dial to select aircraft, ordered by distance. Tap the screen or press the button to open or close details. Hold the button for 1.2 seconds to refresh. The outer ring shows Wi-Fi/feed state; the coral marker shows the selected aircraft on the map. If the feed fails, the last result stays visible with a stale warning and data age.

Main map: real Franca roads in blue, range rings up to **160 NM**, cyan aircraft, and a coral selected aircraft. Markers use `r_dst`, `r_dir`, and `track` from the feed. The geographic basemap ships in the firmware, so the M5Dial does not download map tiles. Map data: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL. `assets/map_franca.png` and `include/map_franca.h` are generated by `tools/build_map.py` from an Overpass JSON extract.

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
