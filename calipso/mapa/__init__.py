"""
calipso/mapa — El modelo de ciudad (spec 2026-08-25).

Lector puro sobre calipso/economia: pliega el libro y devuelve un MODELO
con coordenadas, nunca un dibujo. Ninguna funcion de este paquete escribe
en el libro ni lee el reloj del sistema.

El paquete NO importa nada de entrada: `urbanismo` no depende de la
economia (solo hashlib y math) y esa restriccion vale tambien a nivel de
import, no solo de archivo. Quien quiera `ciudad` lo importa explicito.
"""
from __future__ import annotations
