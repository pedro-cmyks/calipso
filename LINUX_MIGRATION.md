# Migracion a Linux/Bazzite en ROG Ally

Objetivo: dejar Windows como respaldo de unos 80 GB e instalar Bazzite como
sistema principal en el resto del disco.

## Estado actual antes de tocar particiones

- Calipso esta respaldado en GitHub:
  `git@github.com:pedro-cmyks/calipso.git`
- Checkpoint local/remoto:
  `0ee78f5 Checkpoint Calipso before Linux migration`
- Steam fue limpiado: los juegos grandes se pueden reinstalar despues.
- Windows tiene espacio libre suficiente para reducir la particion.
- Plan de disco:
  - Windows: 80 GB
  - Linux/Bazzite: resto del SSD

## Antes de instalar Bazzite

1. Tener un USB de 16 GB o mas. Todo lo del USB se borra.
2. Descargar Bazzite desde la pagina oficial:
   https://bazzite.gg/
3. Elegir imagen para handheld / ASUS ROG Ally.
4. Crear el USB booteable con Rufus o Balena Etcher.
5. Apagar Windows completamente, no suspender.
6. Si BitLocker o Device Encryption esta activo, suspenderlo o guardar la clave
   de recuperacion antes de tocar particiones.
7. Mantener el cargador conectado durante instalacion.

## Arrancar el instalador en ROG Ally

1. Con el equipo apagado, conectar el USB.
2. Mantener `Volume Down` y presionar Power.
3. Al escuchar el sonido de arranque, soltar.
4. En Boot Manager, elegir el USB.

## Instalacion

1. Elegir instalacion manual/custom si pregunta por particiones.
2. No borrar todo el disco.
3. No formatear la particion EFI existente.
4. Reducir Windows a unos 80 GB si el instalador lo permite.
5. Usar el espacio libre/no asignado restante para Bazzite.
6. Si el instalador pregunta por destino de bootloader, usar la EFI existente.
7. Crear usuario normal de Linux para Pedro.

## Primer arranque en Linux

1. Conectarse a Wi-Fi.
2. Abrir Steam e iniciar sesion.
3. Dejar que Bazzite actualice lo que necesite.
4. Probar:
   - audio
   - Wi-Fi
   - Bluetooth
   - controles del ROG Ally
   - suspender/despertar
   - Steam
   - un juego liviano

## Restaurar Calipso en Linux

Abrir terminal:

```bash
mkdir -p ~/projects
cd ~/projects
git clone git@github.com:pedro-cmyks/calipso.git
cd calipso
```

Si SSH no esta configurado aun en Linux:

```bash
ssh-keygen -t ed25519 -C "pedro-calipso-linux"
cat ~/.ssh/id_ed25519.pub
```

Pegar la llave publica en GitHub:
Settings -> SSH and GPG keys -> New SSH key.

Instalar dependencias base:

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install chromadb ollama playwright litellm fastapi "uvicorn[standard]" pyotp qrcode pillow
python -m playwright install chromium
```

Arrancar Calipso:

```bash
# Opcion 1: lanzador (recomendado, activa venv y abre navegador)
./calipso.sh

# Opcion 2: manual
source .venv/bin/activate
python calipso/server.py
```

Abrir en navegador:

```text
http://localhost:8000/
```

Si Calipso pide token/TOTP, habra que recrear la configuracion local o copiar
con cuidado `~/.calipso` desde Windows si se decide migrar memoria runtime.

## Ollama en Linux

Instalar Ollama desde su pagina oficial y bajar modelos:

```bash
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b
ollama pull bge-m3
```

## Cosas que NO borrar hasta estar seguros

- Particion EFI.
- Particion de recuperacion de Windows.
- Windows de 80 GB, hasta que Bazzite lleve varios dias funcionando bien.
- Backups de Calipso y memoria.

## Si algo sale mal

- Desde el Boot Manager se deberia poder elegir Windows.
- Calipso esta en GitHub privado.
- Los juegos de Steam se reinstalan.
- Si Bazzite no arranca, no formatear mas: volver a Windows y diagnosticar.

