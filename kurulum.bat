@echo off
chcp 65001 > nul
echo ================================================
echo   Dentalpazar - Trendyol Kar Takip Sistemi
echo   Kurulum Sihirbazi
echo ================================================
echo.

:: Python kontrolu
python --version > nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi!
    echo.
    echo Lutfen once Python 3.10 veya uzeri yukleyin:
    echo https://www.python.org/downloads/
    echo.
    echo Kurulum sirasinda "Add Python to PATH" secenegini
    echo isaretlemeyi unutmayin!
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] %PYVER% bulundu.
echo.

:: Paketleri yukle
echo Gerekli paketler yukleniyor, lutfen bekleyin...
echo.
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [HATA] Paket yuklemesi basarisiz oldu.
    echo Internete baglandığınızdan emin olun.
    pause
    exit /b 1
)

echo.
echo [OK] Tum paketler basariyla yuklendi.
echo.

:: Masaustu kisayolu olustur
echo Masaustu kisayolu olusturuluyor...
set SCRIPT_DIR=%~dp0
set SHORTCUT_PATH=%USERPROFILE%\Desktop\Dentalpazar Kar Takip.lnk
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT_PATH%'); $sc.TargetPath = '%SCRIPT_DIR%dentalpazar_baslat.bat'; $sc.WorkingDirectory = '%SCRIPT_DIR%'; $sc.IconLocation = 'shell32.dll,14'; $sc.Save()"

echo.
echo ================================================
echo   Kurulum Tamamlandi!
echo ================================================
echo.
echo Masaustunizdeki "Dentalpazar Kar Takip" kisayoluna
echo cift tiklayarak uygulamayi baslatin.
echo.
echo Ilk acilista bir admin hesabi olusturmaniz
echo istenecektir.
echo.
pause
