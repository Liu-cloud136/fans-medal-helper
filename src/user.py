from aiohttp import ClientSession, ClientTimeout
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
    按直播间状态与大航海身份执行点赞、观看任务
    在2025.9更新后，大航海房间每日点赞五次 实际上仍能获得5*1.5(大航海系数加成)=7.5亲密度
    非大航海房间通过点赞来维持灯牌点亮
    所有房间均能通过25 min有效观时来获得30基础亲密度
    """
    def __init__(self, access_token: str, whiteUIDs: str = '', bannedUIDs: str = '', config: dict = {}):
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
                        # 忽略不可转项
                        continue
                return out

            # 如果是字符串，按逗号切分并提取数字
            if isinstance(uids, str):
                # 先去掉常见的方括号、引号等，防止像 "[1,2]" 导致单项无法转 int
                s = uids.strip()
                # 去掉方括号和单/双引号（如果是像 "[1,2]"）
                s = s.strip("[]'\"")
                parts = [p.strip() for p in s.split(",") if p.strip()]
                parts = [p.strip() for p in s.split(",") if p.strip()]
                out = []
                for p in parts:
                    try:
                        out.append(int(p))
                    except Exception:
                        # 尝试从字符串中提取连续数字（比如 "id: 1234"）
                        import re
                        m = re.search(r"(\d+)", p)
                        if m:
                            out.append(int(m.group(1)))
                        # 否则忽略
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
        
        self.uuids = str(uuid.uuid4())
        self.session = ClientSession(timeout=ClientTimeout(total=5), trust_env=True)
        self.api = BiliApi(self, self.session)
        self._current_watch_tasks = []  # 存储所有并行的观看任务
        self._retry_info = {}

        self.log = logger.bind(user=self.name or "未知用户", uid=self.uuids)
        self.log_file = f"logs/{self.uuids}.log"
        self.sink_id = logger.add(
            self.log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            filter=lambda record: record["extra"].get("uid") == self.uuids,
            encoding="utf-8"
        )
    
    
    # ---------- 对当日已完成任务进行本地存储，避免当日重复打开后多次执行 ----------
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
        # 删除旧日期
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
    
    
    # ------------------------- 登录与初始化 -------------------------
    async def loginVerify(self):
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
        like_cd=self.config.get("LIKE_CD",0.3)
        watch_cd=self.config.get("WATCH_TARGET",25)
        
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
        self.like_list = []
        self.watch_list = []

        today = self._now_beijing().strftime("%Y-%m-%d")
        logs = self._load_log().get(today, {})
        WATCH_TARGET = self.config.get("WATCH_TARGET", 25)

        for medal in self.medals:
            uid = medal["medal"]["target_id"]
            if like_cd and uid not in logs.get("like", []) and (medal['medal']['is_lighted']==0 or medal["medal"]["guard_level"]>0):
                self.like_list.append(medal)
            if watch_cd:
                try:
                    watched = await self.api.getWatchLiveProgress(uid) * 5
                    if watched < WATCH_TARGET:
                        self.watch_list.append(medal)
                except Exception as e:
                    self.log.warning(f"{medal['anchor_info']['nick_name']} 获取直播状态失败: {e}")
            
        self.log.success(f"任务列表共 {len(self.medals)} 个粉丝牌(待点赞: {len(self.like_list)}, 待观看: {len(self.watch_list)})\n")


    # ------------------------- 点赞任务 -------------------------
    async def like_room(self, room_id, medal, times=5):
        name = medal["anchor_info"]["nick_name"]
        success_count = 0
        target_id = medal["medal"]["target_id"]
        
        if self._is_task_done(target_id, "like"):
            self.log.info(f"{name} 点赞任务已完成，跳过。")
            return
        
        for i in range(times):
            fail_count = 0
            while fail_count < 3:
                try:
                    await self.api.likeInteractV3(room_id, target_id, self.mid)
                    success_count += 1
                    await asyncio.sleep(self.config.get("LIKE_CD", 0.3))
                    break  # 成功后退出重试循环
                except Exception as e:
                    fail_count += 1
                    self.log.warning(f"{name} 第 {i+1}/{times} 次点赞失败: {e}， 进行重试 (第{fail_count}/3次)")
                    
                    if fail_count < 3:
                        await asyncio.sleep(1)  # 等待1秒后重试
                    else:
                        self.log.error(f"{name} 第 {i+1}/{times} 次点赞连续失败3次，放弃此条。")
                        break

        self.log.success(f"{name} 点赞任务完成 ({success_count}/{times} 次成功)")
        if self.config.get("NOTIFY_DETAIL", 1):
            if success_count == times:
                self.message.append(f"👍 {name}: 点赞 {success_count}/{times} 次全部成功")
            else:
                self.errmsg.append(f"⚠️ {name}: 点赞仅完成 {success_count}/{times} 次")




        
    
    # ------------------------- 观看任务 -------------------------
    async def get_next_watchable(self, watch_list):
        """
        返回列表中最靠前的可观看房间（观看时长未达到25 min）
        """
        WATCH_TARGET = self.config.get("WATCH_TARGET", 25)
        for medal in watch_list.copy():
            uid = medal["medal"]["target_id"]
            room_id = medal["room_info"]["room_id"]

            try:
                watched = await self.api.getWatchLiveProgress(uid) * 5
                if watched >= WATCH_TARGET:
                    watch_list.remove(medal)
                    continue
                if await self.api.get_medal_light_status(uid)==0:
                    status = await self.api.getRoomLiveStatus(room_id)
                    if status == 1:
                        await self.like_room(room_id, medal, times=36)
                    else:
                        await self.like_room(room_id, medal, times=36)
                    if await self.api.get_medal_light_status(uid)==0:
                        self.log.error(f"{medal['anchor_info']['nick_name']} 灯牌点亮失败，已将灯牌放至列表最后")
                        watch_list.remove(medal)
                        watch_list.append(medal)
                        await asyncio.sleep(0)
                        continue
                        
                return medal
                    
            except Exception as e:
                self.log.warning(f"{medal['anchor_info']['nick_name']} 判定是否可观看失败: {e}")
                continue
        return None  # 没有可观看房间
    
    
    async def watch_room(self, medal):
        """
        对单个房间进行观看直到完成或达到最大尝试
        """
        room_id = medal["room_info"]["room_id"]
        name = medal["anchor_info"]["nick_name"]
        target_id = medal["medal"]["target_id"]

        WATCH_TARGET = self.config.get("WATCH_TARGET", 25)
        MAX_ATTEMPTS = self.config.get("WATCH_MAX_ATTEMPTS", 50)
        attempts = 0
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 3
        
        try:
            watched = await self.api.getWatchLiveProgress(target_id) * 5
        except Exception as e:
            self.log.warning(f"{name} 获取观看进度失败: {e}")
            return False
        self.log.info(f"{name} 开始执行观看任务，还需{WATCH_TARGET-watched}分钟有效观看时长")
        
        while True:
            try:
                # 每分钟发送心跳，每5分钟检查一次进度
                await self.api.heartbeat(room_id, target_id)
                consecutive_failures = 0  # 重置连续失败计数
                
                attempts += 1
                if attempts % 5 == 0:  # 每5分钟检查一次进度
                    try:
                        watched = await self.api.getWatchLiveProgress(target_id) * 5
                        self.log.info(f"{name} 当前观看进度: {watched}/{WATCH_TARGET} 分钟")
                        
                        if watched >= WATCH_TARGET:
                            self.log.success(f"{name} 已观看 {watched} 分钟，任务完成")
                            if self.config.get("NOTIFY_DETAIL", 1):
                                self.message.append(f"👁️  {name}: 观看 {watched} 分钟 ✅")
                            return True
                    except Exception as e:
                        self.log.warning(f"{name} 获取观看进度失败: {e}")
                        consecutive_failures += 1
                        
                # 检查是否超过最大尝试次数
                if attempts >= MAX_ATTEMPTS:
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
    
    async def _watch_task_wrapper(self, medal):
        """ 在后台运行单个 watch_room，并在结束后根据返回值从 watch_list 中移除 medal。 """
        name = medal["anchor_info"]["nick_name"]
        try:
            ok = await self.watch_room(medal)
            if ok:
                # 如果 watch_room 成功，则把 medal 从 watch_list 中移除（若仍在列表中）
                try:
                    self.watch_list.remove(medal)
                except ValueError: # 已经被移除则忽略
                    pass
            else:
                # watch_room 返回 False 的情况下，watch_room 本身已经把 medal 放到队尾或记录了日志
                pass
        except asyncio.CancelledError:
            self.log.info(f"{name} 的后台观看任务被取消")
            raise
        except Exception as e:
            self.log.warning(f"{name} 的后台观看任务出现异常: {e}")
        finally:
            # 从当前任务列表中移除自己
            if medal in self._current_watch_tasks:
                self._current_watch_tasks.remove(medal)
            self.log.info(f"{name} 后台观看任务结束，当前并行观看任务数: {len(self._current_watch_tasks)}")

    async def task_loop(self):
        """按直播状态与用户类型执行点赞任务，观看任务作为独立后台任务运行。
        - 重试/重复日志以每 30 分钟为周期节流
        - 不再使用 some_task_attempted，内部用 per-medal 的 next_check 控制请求频率
        """

        # 确保 retry state 已存在（在 __init__ 或 start() 中初始化也可以）
        if not hasattr(self, "_retry_info"):
            self._retry_info = {}

        LOG_INTERVAL = 1800  # 重复日志间隔：30 分钟

        current_day = self._now_beijing().date()  # 记录初始日期

        # ---------- 点赞子循环 ----------
        async def like_loop():
            while self.like_list:
                now = time.time()

                def _key_for(medal):
                    return f"{medal['medal']['target_id']}:{medal['room_info']['room_id']}"

                def _ensure_state(key):
                    st = self._retry_info.get(key)
                    if st is None:
                        st = {"next_check": 0.0, "last_log": 0.0, "fail_count": 0}
                        self._retry_info[key] = st
                    return st

                # 点赞
                for medal in self.like_list.copy():
                    key = _key_for(medal)
                    st = _ensure_state(key)

                    # 跳过还未到下次检查时间的 medal
                    if now < st["next_check"]:
                        continue

                    uid = medal["medal"]["target_id"]
                    room_id = medal["room_info"]["room_id"]
                    guard = medal["medal"]["guard_level"]

                    try:
                        status = await self.api.getRoomLiveStatus(room_id)
                    except Exception as e:
                        # 网络或 API 错误：指数退避，日志每 LOG_INTERVAL 打一次
                        st["fail_count"] += 1
                        backoff = min(LOG_INTERVAL, 2 ** min(st["fail_count"], 10))
                        st["next_check"] = now + backoff
                        if now - st["last_log"] > LOG_INTERVAL:
                            st["last_log"] = now
                            self.log.warning(f"{medal['anchor_info']['nick_name']} 获取房间开播状态失败: {e} （后续 {int(backoff)}s 内不再重试）")
                        continue

                    # 非直播则不点赞：短退避，日志按 LOG_INTERVAL 节流
                    if status != 1:
                        st["fail_count"] += 1
                        st["next_check"] = now + 60  # 状态不符合时短退避
                        if st["fail_count"] == 1 or (now - st["last_log"] > LOG_INTERVAL):
                            st["last_log"] = now
                            if guard > 0:
                                self.log.info(f"{medal['anchor_info']['nick_name']} 未开播，点赞任务加入重试列表")
                        continue

                    # 真正执行点赞 —— 成功后移除 retry 状态并清理列表
                    try:
                        times = 38 if guard == 0 else 36
                        await self.like_room(room_id, medal, times=times)
                    except Exception as e:
                        # 如果点赞内部失败，也按指数退避处理并节流日志
                        st["fail_count"] += 1
                        backoff = min(LOG_INTERVAL, 2 ** min(st["fail_count"], 10))
                        st["next_check"] = now + backoff
                        if now - st["last_log"] > LOG_INTERVAL:
                            st["last_log"] = now
                            self.log.warning(f"{medal['anchor_info']['nick_name']} 点赞失败: {e} （后续 {int(backoff)}s 内不再重试）")
                        continue

                    # 点赞成功：移除 medal，标记完成，清理 retry state
                    try:
                        self.like_list.remove(medal)
                    except ValueError:
                        pass
                    self._mark_task_done(uid, "like")
                    # 清理 retry info
                    if key in self._retry_info:
                        del self._retry_info[key]

                # Per-medal 控制已经大幅减少重复查询与日志，因此 sleep 可以较短，保证对 watch 的响应性
                await asyncio.sleep(5)

        # ---------- 观看管理子循环 ----------
        async def watch_manager_loop():
            MAX_CONCURRENT_WATCH = self.config.get("MAX_CONCURRENT_WATCH", 3)  # 最大并行观看任务数
            
            while self.watch_list or self._current_watch_tasks:
                # 清理已完成的任务
                self._current_watch_tasks = [task for task in self._current_watch_tasks if task in self.watch_list]
                
                # 启动新的观看任务，直到达到最大并行数
                while len(self._current_watch_tasks) < MAX_CONCURRENT_WATCH and self.watch_list:
                    try:
                        watch_medal = await self.get_next_watchable(self.watch_list)
                    except Exception as e:
                        self.log.warning(f"选择可观看房间时出错: {e}")
                        break

                    if watch_medal:
                        # 避免重复启动同一个房间的观看任务
                        if watch_medal not in self._current_watch_tasks:
                            self._current_watch_tasks.append(watch_medal)
                            self.log.info(f"启动并行观看任务: {watch_medal['anchor_info']['nick_name']} (room: {watch_medal['room_info']['room_id']})，当前并行数: {len(self._current_watch_tasks)}/{MAX_CONCURRENT_WATCH}")
                            asyncio.create_task(self._watch_task_wrapper(watch_medal))
                    else:
                        break

                await asyncio.sleep(10)

        # ---------- 主循环：跨天检查 + 启动/管理子任务 ----------
        while True:
            # 跨天检测
            now_day = self._now_beijing().date()
            if now_day != current_day:
                self.log.success(f"检测到北京时间已进入新的一天（{current_day} → {now_day}），正在重新执行任务……")
                try:
                    await self.session.close()
                except Exception:
                    pass
                await asyncio.sleep(5)
                if getattr(self.api, "session", None) and not self.api.session.closed:
                    await self.api.session.close()
                self.api.session = ClientSession(timeout=ClientTimeout(total=5), trust_env=True)
                await self.start()
                return  # 结束旧循环

            # 全部任务空闲且无后台观看，退出
            if not (self.like_list or self.watch_list or self._current_watch_tasks):
                break

            # 启动子任务（如果尚未启动）
            if not hasattr(self, "_like_task") or self._like_task.done():
                self._like_task = asyncio.create_task(like_loop())
            if not hasattr(self, "_watch_manager_task") or self._watch_manager_task.done():
                self._watch_manager_task = asyncio.create_task(watch_manager_loop())

            # 主循环短睡以便周期性检查（如跨天），并不影响后台 watch task
            await asyncio.sleep(5)

        # 退出前尝试取消仍在运行的子任务（若有）
        for tname in ("_like_task", "_watch_manager_task"):
            task = getattr(self, tname, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self.log.info("所有任务处理完成或已无可执行任务，task_loop 退出。")

            
            
    # ------------------------- 主流程控制 -------------------------
    async def start(self):
        """启动任务：初始化本地日志记录→登录→获取勋章列表→循环执行点赞/观看"""
        self._clean_old_logs()

        # 登录验证
        if not self.api.session or self.api.session.closed:
            self.api.session = ClientSession(timeout=ClientTimeout(total=5), trust_env=True)
        if not await self.loginVerify():
            self.errmsg.append(f"❌ {self.name} 登录失败，access_key 可能已过期")
            await self.session.close()
            return

        # 获取勋章列表
        await self.get_medals()
        if not self.medals:
            self.log.info("没有可执行任务的粉丝牌")
            self.message.append(f"ℹ️ {self.name} 没有可执行任务的粉丝牌")
            await self.session.close()
            return

        self.log.info(f"开始执行任务：")

        # 循环执行点赞→观看
        await self.task_loop()

        self.log.success("所有任务执行完成")
        await self.session.close()
        
        # 收集执行结果用于通知
        if self.config.get("NOTIFY_DETAIL", 1):
            self.message.append("✅ 任务执行完成")
            if self.medals:
                self.message.append(f"📊 处理粉丝牌: {len(self.medals)}个")
                # 获取当日完成的任务统计
                today = self._now_beijing().strftime("%Y-%m-%d")
                logs = self._load_log().get(today, {})
                
                like_count = len(logs.get("like", []))
                watch_completed = sum(1 for medal in self.medals if medal["medal"]["target_id"] not in self.watch_list)
                
                self.message.append(f"👍 点赞完成: {like_count}个房间")
                self.message.append(f"👁️  观看完成: {watch_completed}个房间")
        
        # ---- 等待到下一天后自动重启 ----
        cron = self.config.get("CRON", None)
        if cron:
            base_time = self._now_beijing()
            cron_iter = croniter(cron, base_time)
            next_run_time = cron_iter.get_next(datetime)

            sleep_seconds = (next_run_time - base_time).total_seconds()
            self.log.info(f"等待至北京时间 {next_run_time.strftime('%Y-%m-%d %H:%M:%S')} 自动开始新任务（约 {sleep_seconds/3600:.2f} 小时）")

            await asyncio.sleep(sleep_seconds)
            
            if self.api.session and not self.api.session.closed:
                await self.api.session.close()
            self.api.session = ClientSession(timeout=ClientTimeout(total=5), trust_env=True)
            try:
                await self.start()
            except Exception as e:
                self.log.error(f"主任务执行出错：{e}")
                await asyncio.sleep(60)
                await self.start()
