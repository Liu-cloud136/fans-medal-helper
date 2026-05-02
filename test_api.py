import asyncio
import aiohttp
import json

async def test_api():
    print("=" * 50)
    print("测试前后端连通性")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        # 测试1: 健康检查
        print("\n[测试1] 健康检查接口 (/api/health)")
        try:
            async with session.get("http://localhost:8000/api/health") as resp:
                data = await resp.json()
                print(f"  状态码: {resp.status}")
                print(f"  响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
                if resp.status == 200 and data.get("status") == "ok":
                    print("  ✅ 通过")
                else:
                    print("  ❌ 失败")
        except Exception as e:
            print(f"  ❌ 错误: {e}")
        
        # 测试2: 配置接口
        print("\n[测试2] 配置接口 (/api/config)")
        try:
            async with session.get("http://localhost:8000/api/config") as resp:
                data = await resp.json()
                print(f"  状态码: {resp.status}")
                print(f"  响应: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}...")
                if resp.status == 200 and data.get("success"):
                    print("  ✅ 通过")
                else:
                    print("  ❌ 失败")
        except Exception as e:
            print(f"  ❌ 错误: {e}")
        
        # 测试3: 任务状态接口
        print("\n[测试3] 任务状态接口 (/api/task/status)")
        try:
            async with session.get("http://localhost:8000/api/task/status") as resp:
                data = await resp.json()
                print(f"  状态码: {resp.status}")
                print(f"  响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
                if resp.status == 200 and data.get("success"):
                    print("  ✅ 通过")
                else:
                    print("  ❌ 失败")
        except Exception as e:
            print(f"  ❌ 错误: {e}")
    
    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)
    print("\n服务地址:")
    print("  - 前端界面: http://localhost:8000")
    print("  - API文档:  http://localhost:8000/docs")
    print("  - 健康检查: http://localhost:8000/api/health")

if __name__ == "__main__":
    asyncio.run(test_api())
