#define OPTIMIZER_CORE_EXPORTS
#include "optimizer_core.h"

#include <chrono>
#include <condition_variable>
#include <mutex>
#include <queue>
#include <string>
#include <thread>

namespace {
constexpr DWORD kMinEvent = EVENT_SYSTEM_FOREGROUND;
constexpr DWORD kMaxEvent = EVENT_SYSTEM_FOREGROUND;
constexpr auto kForegroundSettleTime = std::chrono::milliseconds(300);

struct EventItem {
    HWND window;
    DWORD process_id;
    uint64_t timestamp;
};

std::mutex g_mutex;
std::mutex g_queue_mutex;
std::condition_variable g_queue_cv;
std::queue<EventItem> g_event_queue;
HWINEVENTHOOK g_hook = nullptr;
TelemetryCallback g_callback = nullptr;
std::thread g_thread;
std::thread g_worker_thread;
DWORD g_thread_id = 0;
HANDLE g_ready_event = nullptr;
bool g_running = false;
bool g_worker_stop = false;
std::wstring g_previous_process;
std::chrono::steady_clock::time_point g_previous_focus_start;

uint64_t unix_time_ms() {
    const auto now = std::chrono::system_clock::now();
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()).count());
}

void copy_text(wchar_t* destination, size_t capacity, const std::wstring& value) {
    if (capacity == 0) {
        return;
    }
    wcsncpy_s(destination, capacity, value.c_str(), _TRUNCATE);
}

std::wstring process_name(DWORD process_id) {
    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, process_id);
    if (!process) {
        return L"";
    }

    wchar_t path[MAX_PATH] = {};
    DWORD length = MAX_PATH;
    std::wstring result;
    if (QueryFullProcessImageNameW(process, 0, path, &length)) {
        result.assign(path, length);
        const size_t separator = result.find_last_of(L"\\/");
        if (separator != std::wstring::npos) {
            result.erase(0, separator + 1);
        }
    }
    CloseHandle(process);
    return result;
}

void emit_foreground_event(const EventItem& item) {
    wchar_t title[512] = {};
    GetWindowTextW(item.window, title, static_cast<int>(std::size(title)));

    const auto now = std::chrono::steady_clock::now();
    uint64_t previous_duration = 0;
    TelemetryCallback callback = nullptr;
    const std::wstring name = process_name(item.process_id);
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        if (!g_previous_process.empty()) {
            previous_duration = static_cast<uint64_t>(
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    now - g_previous_focus_start).count());
        }
        g_previous_process = name;
        g_previous_focus_start = now;
        callback = g_callback;
    }

    if (!callback) {
        return;
    }

    TelemetryData data{};
    data.process_id = item.process_id;
    copy_text(data.process_name, std::size(data.process_name), name);
    copy_text(data.window_title, std::size(data.window_title), title);
    data.timestamp = item.timestamp;
    data.previous_focus_duration_ms = previous_duration;
    callback(data);
}

void worker_thread() {
    while (true) {
        EventItem pending{};
        {
            std::unique_lock<std::mutex> lock(g_queue_mutex);
            g_queue_cv.wait(lock, [] {
                return g_worker_stop || !g_event_queue.empty();
            });
            if (g_worker_stop && g_event_queue.empty()) {
                return;
            }
            pending = g_event_queue.back();
            std::queue<EventItem>().swap(g_event_queue);
        }

        auto settle_deadline = std::chrono::steady_clock::now() + kForegroundSettleTime;
        while (true) {
            std::unique_lock<std::mutex> lock(g_queue_mutex);
            if (g_queue_cv.wait_until(lock, settle_deadline, [] {
                    return g_worker_stop || !g_event_queue.empty();
                })) {
                if (g_worker_stop && g_event_queue.empty()) {
                    return;
                }
                if (!g_event_queue.empty()) {
                    pending = g_event_queue.back();
                    std::queue<EventItem>().swap(g_event_queue);
                    settle_deadline = std::chrono::steady_clock::now()
                        + kForegroundSettleTime;
                    continue;
                }
            }
            lock.unlock();
            emit_foreground_event(pending);
            break;
        }
    }
}

void CALLBACK win_event_proc(
    HWINEVENTHOOK, DWORD event, HWND window, LONG, LONG, DWORD, DWORD) {
    if (event != EVENT_SYSTEM_FOREGROUND || !window) {
        return;
    }

    DWORD process_id = 0;
    GetWindowThreadProcessId(window, &process_id);
    {
        std::lock_guard<std::mutex> lock(g_queue_mutex);
        g_event_queue.push({window, process_id, unix_time_ms()});
    }
    g_queue_cv.notify_one();
}

void event_thread() {
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        g_thread_id = GetCurrentThreadId();
        g_hook = SetWinEventHook(
            kMinEvent, kMaxEvent, nullptr, win_event_proc, 0, 0,
            WINEVENT_OUTOFCONTEXT);
        if (!g_hook) {
            g_running = false;
        }
    }
    SetEvent(g_ready_event);
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        if (!g_hook) {
            g_thread_id = 0;
            return;
        }
    }

    MSG message{};
    BOOL result;
    while ((result = GetMessageW(&message, nullptr, 0, 0)) > 0) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }

    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_hook) {
        UnhookWinEvent(g_hook);
        g_hook = nullptr;
    }
    g_thread_id = 0;
}
}  // namespace

BOOL WINAPI optimizer_start(TelemetryCallback callback) {
    if (!callback) {
        SetLastError(ERROR_INVALID_PARAMETER);
        return FALSE;
    }

    HANDLE ready_event = nullptr;
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        if (g_running) {
            SetLastError(ERROR_ALREADY_INITIALIZED);
            return FALSE;
        }

        g_callback = callback;
        g_previous_process.clear();
        g_previous_focus_start = std::chrono::steady_clock::now();
        g_ready_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        if (!g_ready_event) {
            g_callback = nullptr;
            return FALSE;
        }
        ready_event = g_ready_event;
        {
            std::lock_guard<std::mutex> queue_lock(g_queue_mutex);
            std::queue<EventItem>().swap(g_event_queue);
            g_worker_stop = false;
        }
        g_running = true;
        try {
            g_worker_thread = std::thread(worker_thread);
            g_thread = std::thread(event_thread);
        } catch (...) {
            g_running = false;
            g_worker_stop = true;
            g_queue_cv.notify_all();
            if (g_worker_thread.joinable()) {
                g_worker_thread.join();
            }
            CloseHandle(g_ready_event);
            g_ready_event = nullptr;
            g_callback = nullptr;
            SetLastError(ERROR_NOT_ENOUGH_MEMORY);
            return FALSE;
        }
    }
    WaitForSingleObject(ready_event, INFINITE);

    bool started = false;
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        started = g_running && g_hook != nullptr;
        CloseHandle(g_ready_event);
        g_ready_event = nullptr;
    }
    if (!started) {
        optimizer_stop();
        return FALSE;
    }
    return TRUE;
}

BOOL WINAPI optimizer_stop() {
    std::thread event_thread_to_join;
    std::thread worker_thread_to_join;
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        if (!g_running && !g_thread.joinable() && !g_worker_thread.joinable()) {
            return TRUE;
        }
        g_running = false;
        if (g_thread_id != 0) {
            PostThreadMessageW(g_thread_id, WM_QUIT, 0, 0);
        }
        event_thread_to_join = std::move(g_thread);
        worker_thread_to_join = std::move(g_worker_thread);
    }
    {
        std::lock_guard<std::mutex> lock(g_queue_mutex);
        g_worker_stop = true;
    }
    g_queue_cv.notify_all();
    if (event_thread_to_join.joinable()) {
        event_thread_to_join.join();
    }
    if (worker_thread_to_join.joinable()) {
        worker_thread_to_join.join();
    }
    std::lock_guard<std::mutex> lock(g_mutex);
    g_callback = nullptr;
    return TRUE;
}

BOOL WINAPI optimizer_is_running() {
    std::lock_guard<std::mutex> lock(g_mutex);
    return g_running ? TRUE : FALSE;
}
