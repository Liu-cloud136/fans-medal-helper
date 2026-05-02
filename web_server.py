#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
B站粉丝牌助手 Web 服务
提供 RESTful API 和 Web 界面
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yaml
from loguru import logger

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="B站粉丝牌助手 Web API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_FILE = "users.yaml"
EXAMPLE_CONFIG_FILE = "users.example.yaml"

task_status = {
    "running": False,
    "progress": 0,
    "logs": [],
    "result": None
}


class UserConfig(BaseModel):
    access_key: str
    cookie: Optional[str] = ""
    white_uid: Optional[List[int]] = []
    banned_uid: Optional[List[int]] = []


class RoomConfig(BaseModel):
    user_index: int = 0
    uid: int
    action: str = "add"


class GeneralConfig(BaseModel):
    WATCH_TARGET: Optional[int] = 5
    WATCH_MAX_ATTEMPTS: Optional[int] = 10
    API_RATE_LIMIT: Optional[float] = 0.5
    MAX_API_CONCURRENT: Optional[int] = 3
    NOTIFY_DETAIL: Optional[int] = 1
    SENDKEY: Optional[str] = ""
    PROXY: Optional[str] = ""


def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        if os.path.exists(EXAMPLE_CONFIG_FILE):
            with open(EXAMPLE_CONFIG_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {"USERS": []}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"USERS": []}


def save_config(config: Dict[str, Any]):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


async def run_fans_medal_task():
    global task_status
    task_status["running"] = True
    task_status["progress"] = 0
    task_status["logs"] = []
    task_status["result"] = None
    
    try:
        task_status["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] 开始执行粉丝牌任务...")
        task_status["progress"] = 10
        
        from main import main
        
        class LogCapture:
            def __init__(self):
                self.logs = []
            
            def write(self, msg):
                self.logs.append(msg)
            
            def flush(self):
                pass
        
        log_capture = LogCapture()
        original_stdout = sys.stdout
        sys.stdout = log_capture
        
        await main()
        
        sys.stdout = original_stdout
        task_status["logs"].extend(log_capture.logs)
        task_status["progress"] = 100
        task_status["result"] = "success"
        task_status["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] 任务执行完成！")
        
    except Exception as e:
        task_status["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] 任务执行出错: {str(e)}")
        task_status["result"] = "error"
    finally:
        task_status["running"] = False


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.get("/api/config")
async def get_config():
    try:
        config = load_config()
        return JSONResponse(content={
            "success": True,
            "data": {
                "USERS": config.get("USERS", []),
                "WATCH_TARGET": config.get("WATCH_TARGET", 5),
                "WATCH_MAX_ATTEMPTS": config.get("WATCH_MAX_ATTEMPTS", 10),
                "API_RATE_LIMIT": config.get("API_RATE_LIMIT", 0.5),
                "MAX_API_CONCURRENT": config.get("MAX_API_CONCURRENT", 3),
                "NOTIFY_DETAIL": config.get("NOTIFY_DETAIL", 1),
                "SENDKEY": config.get("SENDKEY", ""),
                "PROXY": config.get("PROXY", "")
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config/users")
async def add_user(user: UserConfig):
    try:
        config = load_config()
        if "USERS" not in config:
            config["USERS"] = []
        
        new_user = {
            "access_key": user.access_key,
            "cookie": user.cookie,
            "white_uid": user.white_uid,
            "banned_uid": user.banned_uid
        }
        config["USERS"].append(new_user)
        save_config(config)
        
        return JSONResponse(content={
            "success": True,
            "message": "用户添加成功",
            "data": {"user_index": len(config["USERS"]) - 1}
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/config/users/{user_index}")
async def update_user(user_index: int, user: UserConfig):
    try:
        config = load_config()
        users = config.get("USERS", [])
        
        if user_index < 0 or user_index >= len(users):
            raise HTTPException(status_code=404, detail="用户不存在")
        
        users[user_index] = {
            "access_key": user.access_key,
            "cookie": user.cookie,
            "white_uid": user.white_uid,
            "banned_uid": user.banned_uid
        }
        save_config(config)
        
        return JSONResponse(content={
            "success": True,
            "message": "用户配置更新成功"
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/config/users/{user_index}")
async def delete_user(user_index: int):
    try:
        config = load_config()
        users = config.get("USERS", [])
        
        if user_index < 0 or user_index >= len(users):
            raise HTTPException(status_code=404, detail="用户不存在")
        
        deleted_user = users.pop(user_index)
        save_config(config)
        
        return JSONResponse(content={
            "success": True,
            "message": f"用户已删除"
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config/rooms")
async def manage_rooms(room_config: RoomConfig):
    try:
        config = load_config()
        users = config.get("USERS", [])
        
        if room_config.user_index < 0 or room_config.user_index >= len(users):
            raise HTTPException(status_code=404, detail="用户不存在")
        
        user = users[room_config.user_index]
        
        if "white_uid" not in user or user["white_uid"] is None:
            user["white_uid"] = []
        
        if room_config.action == "add":
            if room_config.uid not in user["white_uid"]:
                user["white_uid"].append(room_config.uid)
                message = f"房间 {room_config.uid} 已添加到白名单"
            else:
                message = f"房间 {room_config.uid} 已存在于白名单中"
        elif room_config.action == "remove":
            if room_config.uid in user["white_uid"]:
                user["white_uid"].remove(room_config.uid)
                message = f"房间 {room_config.uid} 已从白名单中移除"
            else:
                message = f"房间 {room_config.uid} 不在白名单中"
        else:
            raise HTTPException(status_code=400, detail="无效的操作类型")
        
        save_config(config)
        
        return JSONResponse(content={
            "success": True,
            "message": message,
            "data": {
                "white_uid": user["white_uid"]
            }
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/config/general")
async def update_general_config(config_data: GeneralConfig):
    try:
        config = load_config()
        
        for key, value in config_data.dict().items():
            if value is not None:
                config[key] = value
        
        save_config(config)
        
        return JSONResponse(content={
            "success": True,
            "message": "通用配置更新成功"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/task/status")
async def get_task_status():
    return JSONResponse(content={
        "success": True,
        "data": task_status
    })


@app.post("/api/task/start")
async def start_task(background_tasks: BackgroundTasks):
    if task_status["running"]:
        return JSONResponse(content={
            "success": False,
            "message": "任务正在运行中"
        })
    
    background_tasks.add_task(run_fans_medal_task)
    
    return JSONResponse(content={
        "success": True,
        "message": "任务已启动"
    })


@app.get("/api/logs")
async def get_logs():
    log_files = []
    logs_dir = "logs"
    
    if os.path.exists(logs_dir):
        for filename in os.listdir(logs_dir):
            if filename.endswith(".log"):
                filepath = os.path.join(logs_dir, filename)
                stat = os.stat(filepath)
                log_files.append({
                    "name": filename,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
    
    return JSONResponse(content={
        "success": True,
        "data": log_files
    })


@app.get("/api/logs/{filename}")
async def get_log_content(filename: str):
    logs_dir = "logs"
    filepath = os.path.join(logs_dir, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="日志文件不存在")
    
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    return JSONResponse(content={
        "success": True,
        "data": {
            "filename": filename,
            "content": content
        }
    })


@app.get("/", response_class=HTMLResponse)
async def root():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    index_path = os.path.join(static_dir, "index.html")
    
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>B站粉丝牌助手</title>
            <meta charset="UTF-8">
        </head>
        <body>
            <h1>B站粉丝牌助手 Web 服务</h1>
            <p>API 服务运行中，请访问 <a href="/docs">/docs</a> 查看 API 文档</p>
        </body>
        </html>
        """)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
