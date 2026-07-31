@echo off
title Barreiras em Dados - Primeiro Coletor
cd /d "%~dp0"

echo.
echo BARREIRAS EM DADOS
echo Primeiro teste do coletor
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass ^
  -File "%~dp0scripts\run-first-remote-replay.ps1"

echo.
if errorlevel 1 (
  echo O teste encontrou um erro.
  echo Deixe esta janela aberta e informe ao Codex somente a ultima mensagem.
) else (
  echo Teste finalizado.
)
echo.
pause
