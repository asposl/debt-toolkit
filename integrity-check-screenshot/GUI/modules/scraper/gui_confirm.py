"""GUI 弹窗确认桥接：通过 log_queue 发送 ("CONFIRM", payload) 协议。"""
import threading


def _request_gui_confirm(log_queue, title, message):
    payload = {
        "title": title,
        "message": message,
        "event": threading.Event(),
        "result": False,
    }
    log_queue.put(("CONFIRM", payload))
    payload["event"].wait()
    return payload["result"]
