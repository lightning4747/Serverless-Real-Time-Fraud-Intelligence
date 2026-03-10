import sys
import os
import platform

def send_notification(task_name):
    title = "🛡️ Sentinel-AML Task Complete"
    message = f"Agent finished: {task_name}"
    
    system = platform.system()
    
    if system == "Darwin":  # macOS
        os.system(f"osascript -e 'display notification \"{message}\" with title \"{title}\" sound name \"Crystal\"'")
    elif system == "Windows":
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=5)
    elif system == "Linux":
        os.system(f"notify-send '{title}' '{message}'")
    else:
        print(f"ALARM: {title} - {message}")

if __name__ == "__main__":
    # Kiro passes {{task_name}} as the first argument
    t_name = sys.argv[1] if len(sys.argv) > 1 else "Unknown Task"
    send_notification(t_name)