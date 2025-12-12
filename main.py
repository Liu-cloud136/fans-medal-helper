import sys

MIN_PYTHON = (3, 10)
if sys.version_info < MIN_PYTHON:
    print(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 及以上版本才支持本程序，当前版本: {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)

import json
import os
from loguru import logger
import warnings
import asyncio
import aiohttp
from datetime import datetime
from src import BiliUser


log = logger.bind(user="B站粉丝牌助手")

warnings.filterwarnings(
    "ignore",
    message="The localize method is no longer necessary, as this time zone supports the fold attribute",
)
os.chdir(os.path.dirname(os.path.abspath(__file__)).split(__file__)[0])

try:
    if os.environ.get("USERS"):
        users = json.loads(os.environ.get("USERS"))
    else:
        import yaml

        with open("users.yaml", "r", encoding="utf-8") as f:
            users = yaml.safe_load(f)
    
    # 验证必要字段是否存在
    if "USERS" not in users:
        log.error("配置文件中缺少USERS字段")
        exit(1)
    
    # 参数验证，使用安全的get方法
    like_cd = users.get("LIKE_CD", 0.3)
    watch_target = users.get("WATCH_TARGET", 5)  # 新规：5次×5分钟=25分钟满亲密度
    watch_max_attempts = users.get("WATCH_MAX_ATTEMPTS", 10)  # 新规：大幅减少尝试次数
    wearmedal = users.get("WEARMEDAL", 0)
    max_concurrent_watch = users.get("MAX_CONCURRENT_WATCH", 6)
    notify_detail = users.get("NOTIFY_DETAIL", 1)
    
    assert like_cd >= 0, "LIKE_CD参数错误"
    assert watch_target >= 0, "WATCH_TARGET参数错误"
    assert watch_max_attempts >= watch_target, "WATCH_MAX_ATTEMPTS参数错误，不能小于WATCH_TARGET"
    assert wearmedal in [0, 1], "WEARMEDAL参数错误"
    assert max_concurrent_watch >= 1, "MAX_CONCURRENT_WATCH参数必须大于等于1"
    assert notify_detail in [0, 1], "NOTIFY_DETAIL参数错误，必须为0或1"
    
    config = {
        "LIKE_CD": like_cd,
        "WATCH_TARGET": watch_target,
        "WATCH_MAX_ATTEMPTS": watch_max_attempts,
        "WEARMEDAL": wearmedal,
        "MAX_CONCURRENT_WATCH": max_concurrent_watch,
        "NOTIFY_DETAIL": notify_detail,
        "PROXY": users.get("PROXY"),
        "API_RATE_LIMIT": users.get("API_RATE_LIMIT", 0.5),
        "MAX_API_CONCURRENT": users.get("MAX_API_CONCURRENT", 3),
    }
except Exception as e:
    log.error(f"读取配置文件失败，请检查格式是否正确: {e}")
    exit(1)


@log.catch
async def main():
    messageList = []
    async with aiohttp.ClientSession(trust_env=True) as session:

        # ------------------------------
        # 创建任务
        # ------------------------------
        biliUsers = []
        startTasks = []
        for user in users["USERS"]:
            if user.get("access_key"):
                biliUser = BiliUser(
                    user["access_key"],
                    user.get("white_uid", ""),
                    user.get("banned_uid", ""),
                    config,
                )
                biliUsers.append(biliUser)
                startTasks.append(biliUser.start())  # ✅ 新逻辑入口

        # ------------------------------
        # 并发执行所有用户任务
        # ------------------------------
        try:
            await asyncio.gather(*startTasks, return_exceptions=True)
        except Exception as e:
            log.exception(e)
            messageList.append(f"🚨 任务执行失败: {e}")

        # ------------------------------
        # 收集所有用户的执行结果
        # ------------------------------
        
        # 清理用户资源
        for biliUser in biliUsers:
            try:
                await biliUser.cleanup()
            except Exception as e:
                log.warning(f"清理用户 {biliUser.name} 资源时出错: {e}")
        
        # 构建人性化的通知消息
        success_count = 0
        error_count = 0
        total_like_success = 0
        total_like_attempts = 0
        total_watch_completed = 0
        total_watch_time = 0
        
        # 构建详细的用户结果报告
        user_reports = []
        
        for biliUser in biliUsers:
            user_report = f"\n👤 {biliUser.name}"
            
            if biliUser.errmsg:
                error_count += 1
                user_report += "\n❌ 执行状态: 失败"
                for msg in biliUser.errmsg:
                    # 美化错误消息格式
                    if "登录失败" in msg:
                        user_report += f"\n   🔐 {msg.replace('❌ ', '')}"
                    elif "点赞仅完成" in msg:
                        user_report += f"\n   👍 {msg.replace('⚠️ ', '')}"
                    elif "观看超时" in msg or "观看连续失败" in msg:
                        user_report += f"\n   👁️  {msg.replace('⚠️ ', '').replace('❌ ', '')}"
                    else:
                        user_report += f"\n   ⚠️ {msg}"
                        
            elif biliUser.message:
                success_count += 1
                user_report += "\n✅ 执行状态: 成功"
                
                # 统计用户数据
                user_like_success = 0
                user_like_attempts = 0
                user_watch_time = 0
                user_watch_rooms = 0
                
                for msg in biliUser.message:
                    if "点赞" in msg and "成功" in msg:
                        # 解析点赞消息 "👍 名字: 点赞 5/5 次全部成功"
                        if "全部成功" in msg:
                            parts = msg.split(":")
                            if len(parts) > 1:
                                like_part = parts[1].strip()
                                if "点赞" in like_part:
                                    numbers = like_part.split("点赞")[1].strip().split(" ")[0]
                                    if "/" in numbers:
                                        success, total = numbers.split("/")
                                        user_like_success += int(success)
                                        user_like_attempts += int(total)
                    elif "观看" in msg and "分钟" in msg and "✅" in msg:
                        # 解析观看消息 "👁️  名字: 观看 25 分钟 ✅"
                        if "分钟" in msg:
                            minutes = msg.split("观看")[1].split("分钟")[0].strip()
                            try:
                                user_watch_time += int(minutes)
                                user_watch_rooms += 1
                            except ValueError:
                                pass
                
                # 添加用户统计
                if user_like_attempts > 0:
                    success_rate = (user_like_success / user_like_attempts) * 100
                    user_report += f"\n   📊 点赞任务: {user_like_success}/{user_like_attempts} ({success_rate:.1f}%)"
                    total_like_success += user_like_success
                    total_like_attempts += user_like_attempts
                
                if user_watch_rooms > 0:
                    user_report += f"\n   ⏱️  观看任务: {user_watch_rooms}个房间, 共{user_watch_time}分钟"
                    total_watch_completed += user_watch_rooms
                    total_watch_time += user_watch_time
                
                # 添加其他消息
                for msg in biliUser.message:
                    if "处理粉丝牌" in msg:
                        user_report += f"\n   🎖️  {msg.replace('📊 ', '')}"
                    elif "没有可执行任务的粉丝牌" in msg:
                        user_report += f"\n   ℹ️  {msg.replace('ℹ️ ', '')}"
                    elif "任务执行完成" in msg:
                        continue  # 这个消息我们已经在上面处理了
            
            user_reports.append(user_report)
        
        # 构建最终消息
        if user_reports:
            messageList.append("🎯 B站粉丝牌助手 - 执行报告")
            messageList.append("=" * 40)
            
            # 总体统计
            total_users = len(biliUsers)
            messageList.append(f"📈 执行概况: 成功 {success_count}/{total_users} 个用户")
            
            if error_count > 0:
                messageList.append(f"⚠️  失败用户: {error_count} 个")
            
            # 添加总体任务统计
            if total_like_attempts > 0:
                like_success_rate = (total_like_success / total_like_attempts) * 100
                messageList.append(f"👍 总体点赞: {total_like_success}/{total_like_attempts} ({like_success_rate:.1f}%)")
            
            if total_watch_completed > 0:
                messageList.append(f"👁️  总体观看: {total_watch_completed}个房间, 共{total_watch_time}分钟")
            
            # 添加详细用户报告
            messageList.append("\n📋 详细报告:")
            messageList.extend(user_reports)
            
            # 添加执行时间
            now = datetime.now()
            messageList.append(f"\n⏰ 完成时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')}")
            
            # 添加友好的结束语
            if success_count == total_users:
                messageList.append("\n🎉 所有任务执行完成！明天见~")
            elif success_count > 0:
                messageList.append(f"\n💪 部分任务完成，继续努力！")
            else:
                messageList.append(f"\n😢 今天有点小问题，明天再试试吧~")

        # ------------------------------
        # 消息推送
        # ------------------------------
        if messageList:
            # 格式化消息内容，使用更友好的格式
            formatted_message = "\n".join(messageList)
            log.info(f"准备推送通知内容:\n{formatted_message}")
            
            if users.get("SENDKEY", ""):
                await push_message(session, users["SENDKEY"], formatted_message)

            if users.get("MOREPUSH", ""):
                from onepush import notify
                notifier = users["MOREPUSH"]["notifier"]
                params = users["MOREPUSH"]["params"]
                await notify(
                    notifier,
                    title=f"【B站粉丝牌助手推送】",
                    content=formatted_message,
                    **params,
                    proxy=config.get("PROXY"),
                )
                log.info(f"{notifier} 已推送")
        else:
            log.info("没有生成通知内容，跳过推送")

    log.info("所有任务执行完成。")


async def push_message(session, sendkey, message):
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = {"title": "【B站粉丝牌助手推送】", "desp": message}
    try:
        await session.post(url, data=data)
        log.info("Server酱已推送")
    except Exception as e:
        log.warning(f"Server酱推送失败: {e}")


def run(*args, **kwargs):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
    log.info("任务结束，等待下一次执行。")


if __name__ == "__main__":
    log.info("青龙面板部署模式，执行单次任务。")
    run()
