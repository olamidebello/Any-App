#!/usr/bin/env python3
import sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE']='/var/lib/anyapps/anyapps.sqlite3'
from app import create_app
create_app()
print('Schema ready.')
