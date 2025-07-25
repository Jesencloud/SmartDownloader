#!/usr/bin/env python3
"""
Celery 优化效果测试
"""

import requests
import time
import concurrent.futures
import statistics
from datetime import datetime
import pytest


@pytest.mark.e2e
class CeleryPerformanceTest:
    """Celery 性能测试器"""

    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self.results = []

    def test_single_download(
        self, test_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ):
        """测试单个下载任务"""
        print("🧪 测试单个下载任务...")

        start_time = time.time()

        # 启动下载任务
        download_data = {
            "url": test_url,
            "download_type": "video",
            "format_id": "best",
            "resolution": "720p",
        }

        try:
            response = requests.post(
                f"{self.base_url}/downloads", json=download_data, timeout=10
            )

            if response.status_code == 202:
                result = response.json()
                task_id = result["task_id"]

                # 监控任务状态
                status = self.monitor_task(task_id)

                end_time = time.time()
                duration = end_time - start_time

                test_result = {
                    "test_type": "single_download",
                    "task_id": task_id,
                    "duration": duration,
                    "status": status,
                    "timestamp": datetime.now().isoformat(),
                }

                self.results.append(test_result)

                print("✅ 单个下载测试完成:")
                print(f"   任务ID: {task_id}")
                print(f"   耗时: {duration:.2f} 秒")
                print(f"   状态: {status}")

                return test_result

        except Exception as e:
            print(f"❌ 单个下载测试失败: {e}")
            return None

    def test_concurrent_downloads(self, num_tasks=3):
        """测试并发下载任务"""
        print(f"🧪 测试并发下载任务 (任务数: {num_tasks})...")

        test_urls = [
            "test-video",  # 使用测试模式
            "test-audio",
            "test-video",
        ][:num_tasks]

        start_time = time.time()

        def start_download(url, index):
            download_data = {
                "url": url,
                "download_type": "video" if "video" in url else "audio",
                "format_id": "best",
                "resolution": "720p",
            }

            try:
                response = requests.post(
                    f"{self.base_url}/downloads", json=download_data, timeout=10
                )

                if response.status_code == 202:
                    result = response.json()
                    return {
                        "index": index,
                        "task_id": result["task_id"],
                        "start_time": time.time(),
                    }

            except Exception as e:
                print(f"❌ 启动任务 {index} 失败: {e}")
                return None

        # 并发启动任务
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_tasks) as executor:
            future_to_index = {
                executor.submit(start_download, url, i): i
                for i, url in enumerate(test_urls)
            }

            tasks = []
            for future in concurrent.futures.as_completed(future_to_index):
                result = future.result()
                if result:
                    tasks.append(result)

        if not tasks:
            print("❌ 没有任务成功启动")
            return None

        print(f"✅ 成功启动 {len(tasks)} 个并发任务")

        # 监控所有任务
        task_results = []
        for task in tasks:
            status = self.monitor_task(task["task_id"])
            task_duration = time.time() - task["start_time"]

            task_results.append(
                {
                    "task_id": task["task_id"],
                    "duration": task_duration,
                    "status": status,
                }
            )

        total_duration = time.time() - start_time

        # 统计结果
        durations = [t["duration"] for t in task_results if t["status"] == "SUCCESS"]

        test_result = {
            "test_type": "concurrent_downloads",
            "num_tasks": num_tasks,
            "completed_tasks": len(
                [t for t in task_results if t["status"] == "SUCCESS"]
            ),
            "total_duration": total_duration,
            "avg_task_duration": statistics.mean(durations) if durations else 0,
            "min_task_duration": min(durations) if durations else 0,
            "max_task_duration": max(durations) if durations else 0,
            "task_results": task_results,
            "timestamp": datetime.now().isoformat(),
        }

        self.results.append(test_result)

        print("✅ 并发下载测试完成:")
        print(f"   总任务数: {num_tasks}")
        print(f"   完成任务数: {test_result['completed_tasks']}")
        print(f"   总耗时: {total_duration:.2f} 秒")
        print(f"   平均任务耗时: {test_result['avg_task_duration']:.2f} 秒")

        return test_result

    def monitor_task(self, task_id, timeout=60):
        """监控任务状态"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/downloads/{task_id}")
                if response.status_code == 200:
                    result = response.json()
                    status = result["status"]

                    if status in ["SUCCESS", "FAILURE"]:
                        return status

                time.sleep(2)  # 每2秒检查一次

            except Exception as e:
                print(f"⚠️ 监控任务 {task_id} 时出错: {e}")
                time.sleep(2)

        return "TIMEOUT"

    def test_cancellation_performance(self):
        """测试取消下载的性能"""
        print("🧪 测试取消下载性能...")

        # 启动一个长时间任务
        download_data = {
            "url": "test-video",  # 使用测试模式
            "download_type": "video",
            "format_id": "best",
            "resolution": "1080p",
        }

        try:
            start_time = time.time()

            # 启动下载
            response = requests.post(
                f"{self.base_url}/downloads", json=download_data, timeout=10
            )

            if response.status_code == 202:
                result = response.json()
                task_id = result["task_id"]

                # 等待一点时间让任务开始
                time.sleep(2)

                # 取消任务
                cancel_start = time.time()
                cancel_response = requests.post(
                    f"{self.base_url}/downloads/cancel",
                    json={"task_ids": [task_id]},
                    timeout=10,
                )
                cancel_duration = time.time() - cancel_start

                total_duration = time.time() - start_time

                test_result = {
                    "test_type": "cancellation_performance",
                    "task_id": task_id,
                    "cancel_duration": cancel_duration,
                    "total_duration": total_duration,
                    "cancel_success": cancel_response.status_code == 200,
                    "timestamp": datetime.now().isoformat(),
                }

                if cancel_response.status_code == 200:
                    cancel_result = cancel_response.json()
                    test_result["cleanup_result"] = cancel_result.get(
                        "cleanup_result", {}
                    )

                self.results.append(test_result)

                print("✅ 取消下载测试完成:")
                print(f"   任务ID: {task_id}")
                print(f"   取消耗时: {cancel_duration:.3f} 秒")
                print(f"   总耗时: {total_duration:.2f} 秒")
                print(f"   取消成功: {test_result['cancel_success']}")

                return test_result

        except Exception as e:
            print(f"❌ 取消下载测试失败: {e}")
            return None

    def generate_report(self):
        """生成测试报告"""
        if not self.results:
            print("❌ 没有测试结果")
            return

        print("\n" + "=" * 60)
        print("📊 Celery 优化测试报告")
        print("=" * 60)

        for i, result in enumerate(self.results, 1):
            print(f"\n{i}. {result['test_type'].replace('_', ' ').title()}")
            print("-" * 40)

            if result["test_type"] == "single_download":
                print(f"任务ID: {result['task_id']}")
                print(f"执行时间: {result['duration']:.2f} 秒")
                print(f"最终状态: {result['status']}")

            elif result["test_type"] == "concurrent_downloads":
                print(f"任务总数: {result['num_tasks']}")
                print(f"完成任务: {result['completed_tasks']}")
                print(
                    f"成功率: {result['completed_tasks'] / result['num_tasks'] * 100:.1f}%"
                )
                print(f"总执行时间: {result['total_duration']:.2f} 秒")
                print(f"平均任务时间: {result['avg_task_duration']:.2f} 秒")
                print(f"最快任务: {result['min_task_duration']:.2f} 秒")
                print(f"最慢任务: {result['max_task_duration']:.2f} 秒")

            elif result["test_type"] == "cancellation_performance":
                print(f"任务ID: {result['task_id']}")
                print(f"取消响应时间: {result['cancel_duration']:.3f} 秒")
                print(f"取消成功: {result['cancel_success']}")

                if "cleanup_result" in result:
                    cleanup = result["cleanup_result"]
                    cleaned_files = len(cleanup.get("cleaned_files", []))
                    print(f"清理文件数: {cleaned_files}")

        print(f"\n✅ 测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    """主测试函数"""
    print("🚀 开始 Celery 优化测试")

    tester = CeleryPerformanceTest()

    # 运行测试
    try:
        # 1. 单个下载测试
        # tester.test_single_download()
        # time.sleep(2)

        # 2. 并发下载测试
        tester.test_concurrent_downloads(3)
        time.sleep(2)

        # 3. 取消性能测试
        tester.test_cancellation_performance()

        # 生成报告
        tester.generate_report()

    except KeyboardInterrupt:
        print("\n🛑 测试被用户中断")
        tester.generate_report()

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        tester.generate_report()


if __name__ == "__main__":
    main()
