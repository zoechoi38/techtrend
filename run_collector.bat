@echo off
cd /d "C:\Users\zoech\OneDrive\바탕 화면\졸업작품\techtrend"
.venv\Scripts\python.exe collector.py
.venv\Scripts\python.exe processor.py
.venv\Scripts\python.exe analyzer.py
.venv\Scripts\python.exe forecaster.py