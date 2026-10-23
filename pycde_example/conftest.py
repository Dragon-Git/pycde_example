import sys
from multiprocessing import resource_tracker, shared_memory

from .cocotb_runner import build_rtl


def pytest_sessionstart(session):
    if hasattr(session.config, "workerinput"):  # 仅在主进程执行
        return
    shm = shared_memory.SharedMemory("my_shm", create=True, size=8)
    resource_tracker.unregister(shm._name, "shared_memory")
    shm.close()

    sys.path.append(__file__.replace("conftest.py", ""))
    build_rtl()


def pytest_sessionfinish(session, exitstatus):
    if not hasattr(session.config, "workerinput"):  # 仅在主进程执行
        shm = shared_memory.SharedMemory("my_shm", create=False)
        shm.close()
        shm.unlink()
