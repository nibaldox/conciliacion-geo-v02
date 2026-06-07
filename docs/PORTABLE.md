# Guía de uso: Conciliación Geotécnica Portable

Esta es la versión de escritorio portable de la app. Se distribuye como
un único binario (Windows) o AppImage (Linux) y no requiere instalación.

## Windows

1. Descargá `conciliacion-portable-windows.zip` desde la página de
   releases o desde el artifact de GitHub Actions.
2. Extraé el `.zip` en cualquier carpeta (escritorio, USB, lo que sea).
3. Doble click en `conciliacion.exe`.
4. Si Windows SmartScreen te pregunta, hacé click en **"Más info"** y
   después en **"Ejecutar de todas formas"**. Esto aparece solo la
   primera vez.

## Linux

1. Descargá `conciliacion-portable-linux.AppImage`.
2. Abrí una terminal en la carpeta donde está el archivo.
3. Hacé el binario ejecutable:
   ```bash
   chmod +x conciliacion-portable-linux.AppImage
   ```
4. Ejecutalo:
   ```bash
   ./conciliacion-portable-linux.AppImage
   ```

### Troubleshooting Linux

- **"AppImage no se puede montar"** — Te falta FUSE. En Ubuntu 24.04+
  instalalo con `sudo apt install libfuse2`. En versiones más nuevas de
  Ubuntu, FUSE ya no viene por default.
- **El doble click no hace nada** — Asegurate de haber corrido
  `chmod +x` y de que tu file manager soporte ejecutar AppImages.
  Algunos file managers requieren click derecho → "Ejecutar".
- **"Falta libpython o similar"** — Tu distro tiene glibc < 2.35.
  Necesitás Ubuntu 22.04+, Debian 12+, Fedora 36+, o RHEL 9+.

## Dónde queda tu data

La base de datos, los logs y los archivos subidos se guardan en:

- **Windows**: `%APPDATA%\conciliacion\`
  (típicamente `C:\Users\<tu-usuario>\AppData\Roaming\conciliacion\`)
- **Linux**: `~/.local/share/conciliacion/`

**Importante**: la data NO está dentro del bundle. Si movés o borrás
la carpeta del binario, tu data queda intacta en esa ubicación.

## Cómo ver los logs

Los logs de la app y del backend se guardan en:

- **Windows**: `%APPDATA%\conciliacion\logs\conciliacion.log`
- **Linux**: `~/.local/share/conciliacion/logs/conciliacion.log`

Si la app no arranca o se comporta raro, este archivo es el primer
lugar para mirar.

## Cómo actualizar

1. Descargá el nuevo `.zip` / `.AppImage` de la última versión.
2. Cerrá la app si está abierta.
3. Reemplazá el binario viejo por el nuevo (la data en
   `%APPDATA%` / `~/.local/share/` no se toca).
4. Iniciá la app de nuevo.

## Limitaciones conocidas

- **No hay auto-actualización**: la actualización es manual como se
  describe arriba.
- **Una sola instancia por máquina**: si abrís la app dos veces, la
  segunda detecta que el puerto ya está en uso y se cierra.
- **Puerto 57890 debe estar libre**: si otra aplicación usa ese
  puerto, la app no va a arrancar.
- **Sin firma de código en Windows**: SmartScreen va a mostrar la
  advertencia la primera vez.
- **Sin AppImage firmado en Linux**: algunos sistemas pueden mostrar
  advertencias de seguridad.
