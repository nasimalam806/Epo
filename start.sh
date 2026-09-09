#!/bin/bash
# Dummy web server start karna (Background me)
gunicorn web:app --bind 0.0.0.0:${PORT:-10000} &
# Apna main bot start karna
python bot.py
