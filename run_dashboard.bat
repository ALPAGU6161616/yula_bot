@echo off
echo YULA Bot Dashboard Baslatiliyor...
cd /d "%~dp0"
python -m streamlit run dashboard.py
pause
