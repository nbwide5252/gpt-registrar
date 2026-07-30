import os,json,time
from pathlib import Path
from datetime import datetime
BASE_DIR=Path(__file__).resolve().parent
OUTPUTS=BASE_DIR/'outputs'
SUCCESS_FILE=OUTPUTS/'success_rate.json'
COST_FILE=OUTPUTS/'cost_log.json'
