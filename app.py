from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import json, os, glob

app = FastAPI()
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

@app.get("/")
def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))

@app.get("/api/weeks")
def list_weeks():
    files = sorted(glob.glob(f"{DATA_DIR}/*.json"), reverse=True)
    return [os.path.basename(f).replace(".json", "") for f in files]

@app.get("/api/report/{week}")
def get_report(week: str):
    path = f"{DATA_DIR}/{week}.json"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not found")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
