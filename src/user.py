from aiohttp import ClientSession, ClientTimeout, CookieJar
import asyncio
import sys
import os
import uuid
from loguru import logger
from datetime import datetime, timedelta
import time
from collections import defaultdict
import pytz
import json
import random


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> <blue>{extra[user]}</blue> <level>{message}</level>",
    backtrace=False,
    diagnose=False,
)


class BiliUser:
    """
    按直播间状态与大航海身份执行观看任务
    所有房间均能通过25 min有效观时来获得30基础亲密度
    """
    def __init__(self, access_token: str, whiteUIDs: str = '', bannedUIDs: str = '', config: dict = {},
                 session: ClientSession = None, cookie: str = None):
        from .api import BiliApi
        
        def _parse_uid_input(uids):
            """
            将多种可能的输入规范化为 int 列表。
            支持：
              - None -> []
              - list/tuple -> 逐项尝试 int()
              - str: "1,2,3" 或 "1, 2, 3" 或 "['1','2']" -> 按逗号切分再 int()
            会忽略无法转换为 int 的项（并不会抛异常）。
            """
            if not uids:
                return []
            # 如果已经是 list/tuple：直接尝试转换每一项
            if isinstance(uids, (list, tuple)):
                out = []
                for x in uids:
                    try:
                        out.append(int(x))
                    except Exception:
                        continue
                return out

            # 如果是字符串，按逗号切分并提取数字
            if isinstance(uids, str):
                s = uids.strip()
                s = s.strip("[]'\"")
                parts = [p.strip() for p in s.split(",") if p.strip()]
                out = []
                for p in parts:
                    try:
                        out.append(int(p))
                    except Exception:
                        import re
                        m = re.search(r"(\d+)", p)
                        if m:
                            out.append(int(m.group(1)))
                return out

            # 其他类型（如单个 int）
            try:
                return [int(uids)]
            except Exception:
                return []

        self.access_key = access_token
        self.whiteList = _parse_uid_input(whiteUIDs)
        self.bannedList = _parse_uid_input(bannedUIDs)
        self.config = config

        self.mid, self.name = 0, ""
        self.medals = []
        self.message = []
        self.errmsg = []
        self.is_awake = True
        self.unlighted_medals = []  # 存储未点亮的灯牌信息
        
        # 使用两个 UUID 以兼容心跳接口
        self.uuids = [str(uuid.uuid4()), str(uuid.uuid4())]
        self.session = None
        self.api = None
        self._retry_info = {}
        
        # 添加API调用限流控制
        max_concurrent = self.config.get("MAX_API_CONCURRENT", 3)
        self._api_semaphore = asyncio.Semaphore(max_concurrent)
        self._last_api_call = {}
        self._api_min_interval = self.config.get("API_RATE_LIMIT", 0.5)

        # 为每个用户创建独立的 ClientSession（含独立 CookieJar）
        try:
            timeout = ClientTimeout(total=5)
            # 每个用户单独一个 CookieJar，避免不同用户间 cookie 被覆盖
            self.session = ClientSession(timeout=timeout, trust_env=True, cookie_jar=CookieJar())
            self._owns_session = True
        except Exception as e:
            # 回退（极少发生）——若创建失败再尝试使用外部传入的 session（如果有）
            if session is not None:
                self.session = session
                self._owns_session = False
            else:
                raise

        # 创建日志绑定（在 cookie 注入之前）
        self.log = logger.bind(user=self.name or "未知用户", uid=self.uuids[0])
        
        # 确保logs目录存在
        os.makedirs("logs", exist_ok=True)
        
        self.log_file = f"logs/{self.uuids[0]}.log"
        self.sink_id = logger.add(
            self.log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            filter=lambda record: record["extra"].get("uid") in self.uuids,
            encoding="utf-8"
        )
        
        self.log.info("为该用户创建独立的 ClientSession 与 CookieJar（避免共享 session 导致 cookie 覆盖）")

        # 用户通过配置传入原始 Cookie header 字符串（例如浏览器抓包得到的），尝试注入到 session.cookie_jar
        if cookie:
            try:
                def parse_cookie_str(cookie_str: str) -> dict:
                    pairs = [p.strip() for p in cookie_str.split(";") if "=" in p]
                    out = {}
                    for p in pairs:
                        k, v = p.split("=", 1)
                        out[k.strip()] = v.strip()
                    return out

                cookies = parse_cookie_str(cookie)
                cookies = {k: str(v) for k, v in cookies.items()}
                # update_cookies 接受 dict
                self.session.cookie_jar.update_cookies(cookies)
                self.log.info("已将配置中的 cookie 注入 session.cookie_jar（请确认包含 SESSDATA 与 bili_jct）")
            except Exception as e:
                self.log.warning(f"注入 cookie 失败: {e}")

        # 初始化 API（session 已在上面创建）
        self.api = BiliApi(self, self.session)
    
    def _now_beijing(self):
        return datetime.now(pytz.timezone("Asia/Shanghai"))

    def _log_file(self):
        return os.path.join(os.path.dirname(__file__), f"task_log_{self.access_key}.json")

    def _load_log(self):
        try:
            with open(self._log_file(), "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def _save_log(self, data):
        with open(self._log_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _clean_old_logs(self):
        logs = self._load_log()
        today = self._now_beijing().strftime("%Y-%m-%d")
        for date in list(logs.keys()):
            if date != today:
                del logs[date]
        self._save_log(logs)

    def _is_task_done(self, uid, task_type):
        logs = self._load_log()
        today = self._now_beijing().strftime("%Y-%m-%d")
        return uid in logs.get(today, {}).get(task_type, [])

    def _mark_task_done(self, uid, task_type):
        logs = self._load_log()
        today = self._now_beijing().strftime("%Y-%m-%d")
        logs.setdefault(today, {}).setdefault(task_type, []).append(uid)
        self._save_log(logs)
    
    # ------------------------- API限流控制 -------------------------
    async def _rate_limit_api(self, api_name: str):
        """API调用频率限制"""
        current_time = time.time()
        last_call = self._last_api_call.get(api_name, 0)
        min_interval = self._api_min_interval
        
        if current_time - last_call < min_interval:
            wait_time = min_interval - (current_time - last_call)
            await asyncio.sleep(wait_time)
        
        self._last_api_call[api_name] = time.time()
    
    async def _limited_api_call(self, api_func, *args, **kwargs):
        """带限流的API调用"""
        async with self._api_semaphore:
            api_name = api_func.__name__
            await self._rate_limit_api(api_name)
            
            max_retries = 3
            base_delay = 1
            
            for attempt in range(max_retries):
                try:
                    return await api_func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    
                    delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                    self.log.warning(f"API调用 {api_name} 失败 (第{attempt+1}次): {e}, {delay:.1f}秒后重试")
                    await asyncio.sleep(delay)

    # ------------------------- 登录与初始化 -------------------------
    async def _init_session(self):
        """初始化session和API对象"""
        # 如果 session 已关闭，重新创建
        if not self.session or self.session.closed:
            try:
                self.session = ClientSession(
                    timeout=ClientTimeout(total=5), 
                    trust_env=True, 
                    cookie_jar=CookieJar()
                )
                # 重新初始化 API
                from .api import BiliApi
                self.api = BiliApi(self, self.session)
            except Exception as e:
                self.log.warning(f"重新创建 session 失败: {e}")
                raise

    async def loginVerify(self):
        """登录验证"""
        info = await self.api.loginVerift()
        if info["mid"] == 0:
            self.log.error("登录失败，access_key 可能已过期")
            return False
        self.mid, self.name = info["mid"], info["name"]
        self.log = logger.bind(user=self.name)
        self.log.success(f"{self.name} 登录成功 (UID: {self.mid})")
        return True

    async def get_medals(self):
        """根据白名单/黑名单生成粉丝牌任务列表，保持白名单顺序"""
        self.medals.clear()
        all_medals = {}
        watch_cd = self.config.get("WATCH_TARGET", 5)  # 新规：默认5次即可完成
        
        self.log.info(f"开始获取任务列表，粉丝牌顺序为（排名先后即为执行任务先后）：")
        
        # 先获取全部勋章，用于白名单查找
        async for medal in self.api.getFansMedalandRoomID():
            all_medals[medal["medal"]["target_id"]] = medal

        if self.whiteList:
            for uid in self.whiteList:
                medal = all_medals.get(uid)
                anchor_info = (medal.get("anchor_info") if medal else None)
                if anchor_info:
                    name = anchor_info.get("nick_name", "未知主播")
                    if medal:
                        self.medals.append(medal)
                        self.log.info(f"{name}(uid：{uid})")
                    else:
                        self.log.error(f"白名单 {name}(uid：{uid}) 的粉丝牌 未拥有或被删除，已跳过")
                else:
                    self.log.error(f"白名单 uid：{uid} 对应的主播 不存在，已跳过")
        else:
            # 不使用白名单，添加所有勋章，剔除黑名单
            for uid, medal in all_medals.items():
                anchor_info = medal.get("anchor_info")
                if anchor_info:
                    name = anchor_info.get("nick_name", "未知主播")
                    if uid not in self.bannedList:
                        self.medals.append(medal)
                        self.log.info(f"{name}(uid：{uid})")
                    else:
                        self.log.warning(f"{name}(uid：{uid}) 在黑名单中，已跳过")
                else:
                    self.log.error(f"勋章列表 uid：{uid} 对应的主播 不存在，已跳过")
    
        # 生成待执行任务列表
        self.watch_list = []
        self.unlighted_medals = []  # 重置未点亮灯牌列表

        WATCH_TARGET = self.config.get("WATCH_TARGET", 5)  # 目标观看次数

        for medal in self.medals:
            uid = medal["medal"]["target_id"]
            medal_info = medal.get("medal", {})
            guard_level = medal_info.get("guard_level", 0)
            is_lighted = medal_info.get("is_lighted", 1)
            
            # 记录未点亮的灯牌
            if is_lighted == 0:
                anchor_name = medal.get("anchor_info", {}).get("nick_name", "未知主播")
                self.unlighted_medals.append({
                    "name": anchor_name,
                    "uid": uid
                })
            
            # 观看任务
            if watch_cd:
                try:
                    watched_times = await self.api.getWatchLiveProgress(uid)  # 获取观看次数
                    if watched_times < WATCH_TARGET:  # 比较观看次数
                        self.watch_list.append(medal)
                except Exception as e:
                    self.log.warning(f"{medal['anchor_info']['nick_name']} 获取直播状态失败: {e}")
            
        self.log.success(f"任务列表共 {len(self.medals)} 个粉丝牌(待观看: {len(self.watch_list)})")
        self.log.info(f"观看房间列表: {[m['anchor_info']['nick_name'] for m in self.watch_list]}\n")

    # ------------------------- 观看任务 -------------------------
    async def get_next_watchable(self, watch_list):
        """返回列表中最靠前的可观看房间（观看次数未达到目标）"""
        WATCH_TARGET = self.config.get("WATCH_TARGET", 5)  # 目标观看次数
        for medal in watch_list.copy():
            uid = medal["medal"]["target_id"]
            room_id = medal["room_info"]["room_id"]

            try:
                watched_times = await self.api.getWatchLiveProgress(uid)  # 获取观看次数
                if watched_times >= WATCH_TARGET:
                    # 安全删除已完成的观看任务
                    if medal in watch_list:
                        watch_list.remove(medal)
                    continue
                        
                return medal
                    
            except Exception as e:
                self.log.warning(f"{medal['anchor_info']['nick_name']} 判定是否可观看失败: {e}")
                continue
        return None  # 没有可观看房间
    
    async def watch_room(self, medal):
        """对单个房间进行观看直到完成或达到最大尝试"""
        room_id = medal["room_info"]["room_id"]
        name = medal["anchor_info"]["nick_name"]
        target_id = medal["medal"]["target_id"]

        WATCH_TARGET = self.config.get("WATCH_TARGET", 5)  # 目标观看次数（每次5分钟）
        MAX_ATTEMPTS = self.config.get("WATCH_MAX_ATTEMPTS", 10) * 5  # 最大尝试分钟数
        attempts = 0
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 3
        
        try:
            watched_times = await self.api.getWatchLiveProgress(target_id)  # 获取观看次数
            watched_minutes = watched_times * 5  # 转换为分钟数
        except Exception as e:
            self.log.warning(f"{name} 获取观看进度失败: {e}")
            return False
        self.log.info(f"{name} 开始执行观看任务，还需{WATCH_TARGET-watched_times}次（{WATCH_TARGET*5-watched_minutes}分钟）有效观看时长")
        
        while True:
            try:
                # 检查session是否关闭，如果关闭则重连
                if self.session.closed or not self.api:
                    self.log.warning(f"{name} 检测到session已关闭，重新创建连接")
                    await self._init_session()
                
                # 每分钟发送心跳，每5分钟检查一次进度
                await self._limited_api_call(self.api.heartbeat, room_id, target_id)
                consecutive_failures = 0  # 重置连续失败计数
                
                attempts += 1
                if attempts % 5 == 0:  # 每5分钟检查一次进度
                    try:
                        watched_times = await self._limited_api_call(self.api.getWatchLiveProgress, target_id)  # 获取观看次数
                        watched_minutes = watched_times * 5  # 转换为分钟数
                        self.log.info(f"{name} 当前观看进度: {watched_times}/{WATCH_TARGET} 次（{watched_minutes}/{WATCH_TARGET*5} 分钟）")
                        
                        if watched_times >= WATCH_TARGET:
                            self.log.success(f"{name} 已观看 {watched_times} 次（{watched_minutes} 分钟），任务完成")
                            if self.config.get("NOTIFY_DETAIL", 1):
                                self.message.append(f"👁️  {name}: 观看 {watched_times} 次（{watched_minutes} 分钟）✅")
                            return True
                    except Exception as e:
                        self.log.warning(f"{name} 获取观看进度失败: {e}")
                        consecutive_failures += 1
                        
                # 检查是否超过最大尝试次数
                if attempts >= MAX_ATTEMPTS:
                    # 在判断超时前，先检查当前观看进度
                    try:
                        final_watched = await self._limited_api_call(self.api.getWatchLiveProgress, target_id) * 5
                        if final_watched >= WATCH_TARGET:
                            self.log.success(f"{name} 已观看 {final_watched} 分钟，任务完成")
                            if self.config.get("NOTIFY_DETAIL", 1):
                                self.message.append(f"👁️  {name}: 观看 {final_watched} 分钟 ✅")
                            return True
                    except Exception as e:
                        self.log.warning(f"{name} 获取最终观看进度失败: {e}")
                    
                    # 如果确实超时了
                    self.log.error(f"{name} 超过最大尝试 {MAX_ATTEMPTS} 分钟，停止观看。该灯牌被放至观看队列最后。")
                    if self.config.get("NOTIFY_DETAIL", 1):
                        self.errmsg.append(f"⚠️ {name}: 观看超时，已观看 {attempts}/{MAX_ATTEMPTS} 分钟")
                    if medal in self.watch_list:
                        self.watch_list.remove(medal)
                        self.watch_list.append(medal)
                    return False
                    
                # 检查连续失败次数
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.log.error(f"{name} 连续失败 {MAX_CONSECUTIVE_FAILURES} 次，停止观看任务")
                    if self.config.get("NOTIFY_DETAIL", 1):
                        self.errmsg.append(f"❌ {name}: 观看连续失败 {consecutive_failures} 次")
                    return False
                    
            except Exception as e:
                self.log.warning(f"{name} heartbeat 出错: {e}")
                consecutive_failures += 1
                
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.log.error(f"{name} 连续失败 {MAX_CONSECUTIVE_FAILURES} 次，停止观看任务")
                    if self.config.get("NOTIFY_DETAIL", 1):
                        self.errmsg.append(f"❌ {name}: 观看连续失败 {consecutive_failures} 次")
                    return False

            await asyncio.sleep(60)
    
    async def watch_room_complete(self, medal):
        """执行单个房间的观看任务直到完成（兼容旧接口）"""
        name = medal["anchor_info"]["nick_name"]
        try:
            ok = await self.watch_room(medal)
            if ok:
                # 如果观看成功，则把 medal 从 watch_list 中移除
                try:
                    self.watch_list.remove(medal)
                except ValueError:
                    pass  # 已经被移除则忽略
        except Exception as e:
            self.log.warning(f"{name} 的观看任务出现异常: {e}")
            return False
        return ok

    async def _watch_task_wrapper(self, medal):
        """在后台运行单个 watch_room，并在结束后根据返回值从 watch_list 中移除 medal"""
        name = medal["anchor_info"]["nick_name"]
        try:
            ok = await self.watch_room(medal)
            if ok:
                try:
                    self.watch_list.remove(medal)
                except ValueError:
                    pass
            else:
                pass
        except asyncio.CancelledError:
            self.log.info(f"{name} 的后台观看任务被取消")
            raise
        except Exception as e:
            self.log.warning(f"{name} 的后台观看任务出现异常: {e}")
        finally:
            self._current_watch_task = None
            self.log.info(f"{name} 后台观看任务结束。")

    async def task_loop(self):
        """按直播状态执行观看任务，使用子任务架构
        - 使用独立 day_change_watcher 通过事件通知实现跨天重启
        """
        # 确保 retry state 已存在
        if not hasattr(self, "_retry_info"):
            self._retry_info = {}

        # day change event：由 watcher 设置，start() 会根据这个事件决定是否重启
        self._day_changed_event = asyncio.Event()

        # ---------- 跨天监测子任务 ----------
        async def day_change_watcher():
            current_day = self._now_beijing().date()
            while True:
                await asyncio.sleep(5)
                now_day = self._now_beijing().date()
                if now_day != current_day:
                    self.log.success(f"检测到北京时间已进入新的一天（{current_day} → {now_day}），准备重新执行任务……")
                    # 标记跨天事件，由上层 start() 处理重启流程
                    self._day_changed_event.set()
                    return

        # ---------- 观看管理子循环 ----------
        async def watch_manager_loop():
            while self.watch_list or getattr(self, "_current_watch_task", None):
                if getattr(self, "_current_watch_task", None) is None and self.watch_list:
                    try:
                        watch_medal = await self.get_next_watchable(self.watch_list)
                    except Exception as e:
                        self.log.warning(f"选择可观看房间时出错: {e}")
                        watch_medal = None

                    if watch_medal:
                        self.log.info(f"启动观看任务: {watch_medal['anchor_info']['nick_name']} (room: {watch_medal['room_info']['room_id']})")
                        # 启动后台观看任务
                        self._current_watch_task = asyncio.create_task(
                            self._watch_task_wrapper(watch_medal)
                        )

                await asyncio.sleep(10)

        # ---------- 观看任务包装器 ----------
        async def _watch_task_wrapper(medal):
            """在后台运行单个 watch_room，并在结束后根据返回值从 watch_list 中移除 medal"""
            name = medal["anchor_info"]["nick_name"]
            try:
                ok = await self.watch_room(medal)
                if ok:
                    # 如果 watch_room 成功，则把 medal 从 watch_list 中移除（若仍在列表中）
                    try:
                        self.watch_list.remove(medal)
                    except ValueError:
                        pass  # 已经被移除则忽略
                else:
                    # watch_room 返回 False 的情况下，watch_room 本身已经把 medal 放到队尾或记录了日志
                    pass
            except asyncio.CancelledError:
                self.log.info(f"{name} 的后台观看任务被取消")
                raise
            except Exception as e:
                self.log.warning(f"{name} 的后台观看任务出现异常: {e}")
            finally:
                self._current_watch_task = None
                self.log.info(f"{name} 后台观看任务结束。")

        # ---------- 启动并管理子任务 ----------
        # 启动 day watcher
        if not hasattr(self, "_day_watch_task") or self._day_watch_task.done():
            self._day_watch_task = asyncio.create_task(day_change_watcher())

        # 循环检查子任务与退出条件（当 day change 触发或任务全部完成时退出）
        try:
            while True:
                # 若跨天事件触发，立即中止循环以便上层 start() 进行重启
                if getattr(self, "_day_changed_event", None) and self._day_changed_event.is_set():
                    break

                # 全部任务空闲且无后台观看，退出
                if not (self.watch_list or getattr(self, "_current_watch_task", None)):
                    break

                # 启动观看管理子任务（如果尚未启动或已结束）
                if not hasattr(self, "_watch_manager_task") or self._watch_manager_task.done():
                    self._watch_manager_task = asyncio.create_task(watch_manager_loop())

                # 主循环短睡以便周期性检查（如跨天）
                await asyncio.sleep(5)
        finally:
            # 退出前尝试取消仍在运行的子任务（若有）
            for tname in ("_watch_manager_task", "_day_watch_task"):
                task = getattr(self, tname, None)
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        self.log.info("task_loop 退出。")
        return

    async def cleanup(self):
        """清理资源"""
        try:
            # 关闭session
            if self.session and not self.session.closed:
                await self.session.close()
                
            self.log.info("资源清理完成")
        except Exception as e:
            self.log.warning(f"资源清理时出错: {e}")

    # ------------------------- 主流程控制 -------------------------
    async def start(self):
        """启动任务：初始化本地日志记录→登录→获取勋章列表→循环执行观看任务
        start 会在跨天触发（任务未全部执行完成）时立即重新开始（即时重启到新的一天）
        """
        # 清理旧日志
        self._clean_old_logs()

        # 循环直到不需要继续（由跨天决定）
        while True:
            # 登录验证
            if not await self.loginVerify():
                try:
                    if getattr(self, "session", None) and not self.session.closed:
                        await self.session.close()
                except Exception:
                    pass
                return

            # 获取勋章列表
            await self.get_medals()
            if not self.medals:
                self.log.info("没有可执行任务的粉丝牌")
                self.message.append(f"ℹ️ {self.name} 没有可执行任务的粉丝牌")
                try:
                    if getattr(self, "session", None) and not self.session.closed:
                        await self.session.close()
                except Exception:
                    pass
                return

            self.log.info("开始执行任务：")

            # 调用主循环（阻塞直到任务完成或跨天事件触发）
            await self.task_loop()

            # 如果是跨天触发，立即重新开始
            if getattr(self, "_day_changed_event", None) and self._day_changed_event.is_set():
                # 清理旧 session 并立即重启新一天的任务流程
                try:
                    if getattr(self.api, "session", None) and not self.api.session.closed:
                        await self.api.session.close()
                except Exception:
                    pass

                self.log.info("检测到跨天，已退出以等待外部调度器/下一次 run() 触发新任务。")
                return

            # 否则，任务为"正常完成"
            self.log.success("🎉 所有任务执行完成")
            try:
                if getattr(self.api, "session", None) and not self.api.session.closed:
                    await self.api.session.close()
            except Exception:
                pass

            # 收集执行结果用于通知
            if self.config.get("NOTIFY_DETAIL", 1):
                if not self.medals:
                    self.message.append("ℹ️  没有可执行任务的粉丝牌")
                else:
                    self.message.append("✅ 任务执行完成")
                    self.message.append(f"🎖️  处理粉丝牌: {len(self.medals)}个")
                    watch_completed = sum(1 for medal in self.medals if medal["medal"]["target_id"] not in self.watch_list)
                    if watch_completed > 0:
                        self.message.append(f"👁️  观看完成: {watch_completed}个房间")

            return