# Calipso - runbook de arranque

## Si localhost esta caido

Significa que el servidor de Calipso no esta prendido. No es que la app se haya
perdido: hay que arrancarla.

En Windows, doble clic:

```text
Calipso.bat
```

O desde PowerShell:

```powershell
.\Calipso.ps1
```

O en cualquier sistema con Python:

```bash
python launch_calipso.py
```

Si PowerShell responde que `python` o `py` no existen, el problema es PATH o una
instalacion de Python no visible para la terminal. En ese caso:

1. Buscar el ejecutable real de Python en Windows.
2. Agregarlo a PATH o ajustar `Calipso.bat`/`Calipso.ps1` para llamar esa ruta
   exacta.
3. Volver a probar `python --version` desde una terminal nueva.

El lanzador:

1. revisa si Calipso ya esta prendido;
2. si no, arranca `calipso/server.py`;
3. espera a que responda;
4. abre el navegador con el token de recuperacion;
5. deja una ventana viva mientras usas Calipso.

## URL local

```text
http://localhost:8000
```

Si pide login, usa tu TOTP. Si necesitas recuperacion, el token esta en:

```text
~/.calipso/token
```

## Celular

En la misma red local:

```text
http://192.168.1.10:8000
```

Para usarlo fuera de casa, la ruta correcta es Tailscale, no abrir el puerto a
internet.

## PWA

Calipso ya declara manifest y service worker:

```text
/manifest.json
/sw.js
```

Cuando lo abras desde el navegador del celular, deberia poder instalarse como app
si el navegador/plataforma lo permite.

## Cerrar Calipso

Cierra la ventana de consola del lanzador, o presiona `Ctrl+C`.

## Regla de producto

Calipso debe sentirse como aplicacion. Si Pedro tiene que acordarse de comandos,
falta producto. El objetivo futuro es:

- app nativa en Windows/macOS con Tauri/Electron o lanzador empaquetado;
- PWA instalable en celular;
- arranque automatico opcional;
- health check visible;
- boton "abrir Calipso" sin tocar terminal.
