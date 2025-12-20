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
        
        self.uuids = str(uuid.uuid4())
        self.session = None
        self.api = None
        self._retry_info = {}
        
        # 添加API调用限流控制
        max_concurrent = self.config.get("MAX_API_CONCURRENT", 3)
        self._api_semaphore = asyncio.Semaphore(max_concurrent)
        self._last_api_call = {}
        self._api_min_interval = self.config.get("API_RATE_LIMIT", 0.5)

        self.log = logger.bind(user=self.name or "未知用户", uid=self.uuids)
        
        # 确保logs目录存在
        os.makedirs("logs", exist_ok=True)
        
        self.log_file = f"logs/{self.uuids}.log"
        self.sink_id = logger.add(
            self.log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            filter=lambda record: record["extra"].get("uid") == self.uuids,
            encoding="utf-8"
        )
    
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
        if not self.session or self.session.closed:
            self.session = ClientSession(timeout=ClientTimeout(total=5), trust_env=True)
            from .api import BiliApi
            self.api = BiliApi(self, self.session)

    async def loginVerify(self):
        await self._init_session()
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
        like_cd = self.config.get("LIKE_CD", 0.3)
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
        self.like_list = []
        self.watch_list = []

        today = self._now_beijing().strftime("%Y-%m-%d")
        logs = self._load_log().get(today, {})
        WATCH_TARGET = self.config.get("WATCH_TARGET", 5) * 5  # 修正：将次数转换为分钟数

        for medal in self.medals:
            uid = medal["medal"]["target_id"]
            medal_info = medal.get("medal", {})
            guard_level = medal_info.get("guard_level", 0)
            is_lighted = medal_info.get("is_lighted", 1)
            
            # 点赞任务：未完成点赞
            # 策略：大航海房间每天点赞获得额外亲密度，普通房间点赞维持灯牌点亮
            if like_cd and uid not in logs.get("like", []):
                # 对所有未完成点赞的房间执行点赞任务
                self.like_list.append(medal)
                
            # 观看任务
            if watch_cd:
                try:
                    watched = await self.api.getWatchLiveProgress(uid) * 5
                    if watched < WATCH_TARGET * 5:  # 修正：将次数转换为分钟数
                        self.watch_list.append(medal)
                except Exception as e:
                    self.log.warning(f"{medal['anchor_info']['nick_name']} 获取直播状态失败: {e}")
            
        self.log.success(f"任务列表共 {len(self.medals)} 个粉丝牌(待点赞: {len(self.like_list)}, 待观看: {len(self.watch_list)})")
        self.log.info(f"点赞房间列表: {[m['anchor_info']['nick_name'] for m in self.like_list]}")
        self.log.info(f"观看房间列表: {[m['anchor_info']['nick_name'] for m in self.watch_list]}\n")

    # ------------------------- 点赞任务 -------------------------
    async def like_room(self, room_id, medal, times=5):
        name = medal["anchor_info"]["nick_name"]
        success_count = 0
        target_id = medal["medal"]["target_id"]
        
        if self._is_task_done(target_id, "like"):
            self.log.info(f"{name} 点赞任务已完成，跳过。")
            return success_count
        
        for i in range(times):
            fail_count = 0
            while fail_count < 3:
                try:
                    await self._limited_api_call(self.api.likeInteractV3, room_id, target_id, self.mid)
                    success_count += 1
                    # 增加随机延迟，避免固定间隔
                    delay = self.config.get("LIKE_CD", 0.3) + random.uniform(0.1, 0.5)
                    await asyncio.sleep(delay)
                    break  # 成功后退出重试循环
                except Exception as e:
                    fail_count += 1
                    self.log.warning(f"{name} 第 {i+1}/{times} 次点赞失败: {e}， 进行重试 (第{fail_count}/3次)")
                    
                    if fail_count < 3:
                        await asyncio.sleep(1 + random.uniform(0.5, 1.5))  # 随机延迟1-2.5秒后重试
                    else:
                        self.log.error(f"{name} 第 {i+1}/{times} 次点赞连续失败3次，放弃此条。")
                        break

        self.log.success(f"{name} 点赞任务完成 ({success_count}/{times} 次成功)")
        if self.config.get("NOTIFY_DETAIL", 1):
            if success_count == times:
                self.message.append(f"👍 {name}: 点赞 {success_count}/{times} 次全部成功")
            else:
                success_rate = (success_count / times) * 100 if times > 0 else 0
                self.errmsg.append(f"⚠️ {name}: 点赞仅完成 {success_count}/{times} 次 ({success_rate:.0f}%)")
        
        return success_count

    # ------------------------- 观看任务 -------------------------
    async def get_next_watchable(self, watch_list):
        """返回列表中最靠前的可观看房间（观看时长未达到25 min）"""
        WATCH_TARGET = self.config.get("WATCH_TARGET", 5) * 5  # 修正：将次数转换为分钟数
        for medal in watch_list.copy():
            uid = medal["medal"]["target_id"]
            room_id = medal["room_info"]["room_id"]

            try:
                watched = await self.api.getWatchLiveProgress(uid) * 5
                if watched >= WATCH_TARGET:
                    # 安全删除已完成的观看任务
                    if medal in watch_list:
                        watch_list.remove(medal)
                    continue
                    
                # 检查灯牌状态，但不在这里点赞，避免与点赞任务冲突
                medal_light_status = await self.api.get_medal_light_status(uid)
                if medal_light_status == 0:
                    self.log.warning(f"{medal['anchor_info']['nick_name']} 灯牌未点亮，点赞任务将处理，暂不开始观看")
                    # 将未点亮的房间移到列表最后，优先处理点赞
                    if medal in watch_list:
                        watch_list.remove(medal)
                        watch_list.append(medal)
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

        WATCH_TARGET = self.config.get("WATCH_TARGET", 5) * 5  # 修正：将次数转换为分钟数
        MAX_ATTEMPTS = self.config.get("WATCH_MAX_ATTEMPTS", 10) * 5  # 修正：将尝试次数转换为分钟数
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
                        watched = await self._limited_api_call(self.api.getWatchLiveProgress, target_id) * 5
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
    
    async def watch_room_complete(self, medal):
        """执行单个房间的观看任务直到完成"""
        name = medal["anchor_info"]["nick_name"]
        try:
            ok = await self.watch_room(medal)
            if ok:
                # 如果观看成功，则把 medal 从 watch_list 中移除
                try:
                    self.watch_list.remove(medal)
                except ValueError: # 已经被移除则忽略
                    pass
        except Exception as e:
            self.log.warning(f"{name} 的观看任务出现异常: {e}")
            return False
        return ok

    async def task_loop(self):
        """按直播状态与用户类型执行点赞和观看任务，串行执行"""
        # 确保 retry state 已存在
        if not hasattr(self, "_retry_info"):
            self._retry_info = {}

        LOG_INTERVAL = 1800  # 重复日志间隔：30 分钟
        current_day = self._now_beijing().date()  # 记录初始日期

        # ---------- 主循环 ----------
        while True:
            # 跨天检测
            now_day = self._now_beijing().date()
            if now_day != current_day:
                self.log.success(f"检测到北京时间已进入新的一天（{current_day} → {now_day}），正在重新执行任务……")
                try:
                    if self.session:
                        await self.session.close()
                except Exception:
                    pass
                await asyncio.sleep(5)
                await self._init_session()
                # 重新获取任务列表而不是递归调用start()
                await self.get_medals()
                current_day = now_day
                continue  # 继续主循环而不是递归

            # 点赞任务处理
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

                # 获取当前待处理的medal
                medaled_to_process = None
                for medal in self.like_list:
                    key = _key_for(medal)
                    st = _ensure_state(key)

                    if now < st["next_check"]:
                        continue

                    medaled_to_process = medal
                    break

                if not medaled_to_process:
                    await asyncio.sleep(5)
                    continue

                medal = medaled_to_process
                key = _key_for(medal)
                st = _ensure_state(key)

                uid = medal["medal"]["target_id"]
                room_id = medal["room_info"]["room_id"]
                guard = medal["medal"]["guard_level"]
                name = medal["anchor_info"]["nick_name"]

                self.log.info(f"开始执行 {name} 点赞任务 (大航海等级: {guard})")
                
                try:
                    # 新规调整：点赞每日可获得1航海亲密度，上限5亲密度
                    # 普通房间：点赞5次（维持灯牌和获得基础亲密度）
                    # 大航海房间：点赞5次（获得1.5倍加成的亲密度）
                    times = 5  # 新规：统一5次点赞即可获得每日上限
                    success_count = await self.like_room(room_id, medal, times=times)
                    
                    self.like_list.remove(medal)
                    self._mark_task_done(uid, "like")
                    if key in self._retry_info:
                        del self._retry_info[key]
                    
                    self.log.info(f"{name} 点赞任务完成，成功 {success_count}/{times} 次，剩余待点赞: {len(self.like_list)}")
                        
                except Exception as e:
                    st["fail_count"] += 1
                    backoff = min(LOG_INTERVAL, 2 ** min(st["fail_count"], 10))
                    st["next_check"] = now + backoff
                    if now - st["last_log"] > LOG_INTERVAL:
                        st["last_log"] = now
                        self.log.warning(f"{medal['anchor_info']['nick_name']} 点赞失败: {e} （后续 {int(backoff)}s 内不再重试）")

                await asyncio.sleep(2)

            # 观看任务处理（串行执行）
            while self.watch_list:
                try:
                    watch_medal = await self.get_next_watchable(self.watch_list)
                except Exception as e:
                    self.log.warning(f"选择可观看房间时出错: {e}")
                    break

                if not watch_medal:
                    break

                name = watch_medal["anchor_info"]["nick_name"]
                self.log.info(f"开始观看任务: {name} (room: {watch_medal['room_info']['room_id']})")
                await self.watch_room_complete(watch_medal)

            # 全部任务空闲，退出
            if not (self.like_list or self.watch_list):
                break

            await asyncio.sleep(5)

        self.log.info("所有任务处理完成或已无可执行任务，task_loop 退出。")

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
        """启动任务：初始化本地日志记录→登录→获取勋章列表→循环执行点赞/观看"""
        self._clean_old_logs()

        # 登录验证
        await self._init_session()
        if not await self.loginVerify():
            self.errmsg.append(f"❌ {self.name} 登录失败，access_key 可能已过期")
            if self.session:
                await self.session.close()
            return

        # 获取勋章列表
        await self.get_medals()
        if not self.medals:
            self.log.info("没有可执行任务的粉丝牌")
            self.message.append(f"ℹ️ {self.name} 没有可执行任务的粉丝牌")
            if self.session:
                await self.session.close()
            return

        self.log.info(f"🚀 开始执行任务：")

        # 循环执行点赞→观看
        await self.task_loop()

        self.log.success("🎉 所有任务执行完成")
        if self.session:
            await self.session.close()
        
        # 收集执行结果用于通知
        if self.config.get("NOTIFY_DETAIL", 1):
            if not self.medals:
                self.message.append("ℹ️  没有可执行任务的粉丝牌")
            else:
                self.message.append("✅ 任务执行完成")
                self.message.append(f"🎖️  处理粉丝牌: {len(self.medals)}个")
                # 获取当日完成的任务统计
                today = self._now_beijing().strftime("%Y-%m-%d")
                logs = self._load_log().get(today, {})
                
                like_count = len(logs.get("like", []))
                watch_completed = sum(1 for medal in self.medals if medal["medal"]["target_id"] not in self.watch_list)
                
                if like_count > 0:
                    self.message.append(f"👍 点赞完成: {like_count}个房间")
                if watch_completed > 0:
                    self.message.append(f"👁️  观看完成: {watch_completed}个房间")