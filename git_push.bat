@echo off
set /p msg="Escribe el mensaje para este commit: "
if "%msg%"=="" set msg="Actualizacion automatica DowP"

echo.
echo [+] Anadiendo archivos...
git add .

echo [+] Creando commit: %msg%
git commit -m "%msg%"

echo [+] Subiendo a GitHub...
git push origin main

echo.
echo [!] Proceso terminado.
pause
