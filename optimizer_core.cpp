#define OPTIMIZER_CORE_EXPORTS
#include "optimizer_core.h"

#include <chrono>
#include <mutex>
#include <string>
#include <thread>

namespace {
constexpr DWORD kHoldTimeMs = 2000;
constexpr uint32_t kFocusEvent = 0;
constexpr uint32_t kPromotionEvent = 1;
constexpr uint32_t kResetEvent = 2;
constexpr uint32_t kAbortEvent = 3;

std::mutex g_mutex;
HWINEVENTHOOK g_hook = nullptr;
PTP_TIMER g_timer = nullptr;
HANDLE g_promoted_process = nullptr;
DWORD g_target_process_id = 0;
TelemetryCallback g_callback = nullptr;
std::thread g_thread;
DWORD g_thread_id = 0;
HANDLE g_ready_event = nullptr;
bool g_running = false;
bool g_timer_armed = false;

uint64_t unix_time_ms() {
    const auto now = std::chrono::system_clock::now();
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()).count());
}

void copy_text(wchar_t* destination, size_t capacity, const std::wstring& value) {
    if (capacity != 0) {
        wcsncpy_s(destination, capacity, value.c_str(), _TRUNCATE);
    }
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

void emit_event(DWORD process_id, HWND window, uint32_t event_id,
                uint32_t event_status, uint64_t focus_duration_ms) {
    TelemetryCallback callback = nullptr;
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        callback = g_callback;
    }
    if (!callback) {
        return;
    }

    wchar_t title[512] = {};
    if (window) {
        GetWindowTextW(window, title, static_cast<int>(std::size(title)));
    }
    const std::wstring name = process_name(process_id);
    TelemetryData data{};
    data.process_id = process_id;
    copy_text(data.process_name, std::size(data.process_name), name);
    copy_text(data.window_title, std::size(data.window_title), title);
    data.timestamp = unix_time_ms();
    data.previous_focus_duration_ms = focus_duration_ms;
    data.active_focus_duration_ms = focus_duration_ms;
    data.event_id = event_id;
    data.event_status = event_status;
    callback(data);
}

void cancel_timer_locked() {
    if (g_timer) {
        SetThreadpoolTimer(g_timer, nullptr, 0, 0);
    }
}

DWORD revert_promoted_locked() {
    if (!g_promoted_process) {
        return 0;
    }
    SetPriorityClass(g_promoted_process, NORMAL_PRIORITY_CLASS);
    const DWORD process_id = g_target_process_id;
    CloseHandle(g_promoted_process);
    g_promoted_process = nullptr;
    return process_id;
}

void CALLBACK timer_callback(PTP_CALLBACK_INSTANCE, void*, PTP_TIMER) {
    DWORD process_id = 0;
    HWND window = nullptr;
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        if (!g_running) {
            return;
        }
        window = GetForegroundWindow();
        DWORD foreground_pid = 0;
        GetWindowThreadProcessId(window, &foreground_pid);
        g_timer_armed = false;
        if (foreground_pid != g_target_process_id) {
            return;
        }
        process_id = g_target_process_id;
        HANDLE process = OpenProcess(PROCESS_SET_INFORMATION, FALSE, process_id);
        if (!process || !SetPriorityClass(process, HIGH_PRIORITY_CLASS)) {
            if (process) {
                CloseHandle(process);
            }
            return;
        }
        g_promoted_process = process;
    }
    emit_event(process_id, window, kPromotionEvent, kPromotionEvent, kHoldTimeMs);
}

void on_window_focus_changed(HWND window) {
    DWORD process_id = 0;
    GetWindowThreadProcessId(window, &process_id);
    const std::wstring name = process_name(process_id);
    const bool excluded = !process_id || name.empty() ||
        name == L"explorer.exe" || name == L"cmd.exe" ||
        name == L"conhost.exe" || name == L"system.exe" ||
        name == L"smss.exe" || name == L"csrss.exe" ||
        name == L"wininit.exe" || name == L"services.exe";

    DWORD reverted_process_id = 0;
    DWORD aborted_process_id = 0;
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        if (g_timer_armed && !g_promoted_process) {
            aborted_process_id = g_target_process_id;
        }
        cancel_timer_locked();
        g_timer_armed = false;
        reverted_process_id = revert_promoted_locked();
        if (excluded) {
            g_target_process_id = 0;
        } else {
            g_target_process_id = process_id;
        }
        if (!excluded && g_timer) {
            FILETIME due_time{};
            const LONGLONG relative_100ns =
                -static_cast<LONGLONG>(kHoldTimeMs) * 10000;
            ULARGE_INTEGER relative_time{};
            relative_time.QuadPart = static_cast<ULONGLONG>(relative_100ns);
            due_time.dwLowDateTime = static_cast<DWORD>(relative_time.LowPart);
            due_time.dwHighDateTime = static_cast<DWORD>(relative_time.HighPart);
            SetThreadpoolTimer(g_timer, &due_time, 0, 0);
            g_timer_armed = true;
        }
    }
    if (reverted_process_id) {
        emit_event(reverted_process_id, nullptr, kResetEvent, kResetEvent, 0);
    }
    if (aborted_process_id) {
        emit_event(aborted_process_id, nullptr, kAbortEvent, kAbortEvent, 0);
    }
    emit_event(process_id, window, kFocusEvent, kFocusEvent, 0);
}

void CALLBACK win_event_proc(
    HWINEVENTHOOK, DWORD event, HWND window, LONG, LONG, DWORD, DWORD) {
    if (event == EVENT_SYSTEM_FOREGROUND && window) {
        on_window_focus_changed(window);
    }
}

void event_thread() {
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        g_thread_id = GetCurrentThreadId();
        g_hook = SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, nullptr,
            win_event_proc, 0, 0, WINEVENT_OUTOFCONTEXT);
        if (!g_hook) {
            g_running = false;
        }
    }
    SetEvent(g_ready_event);
    if (!g_hook) {
        std::lock_guard<std::mutex> lock(g_mutex);
        g_thread_id = 0;
        return;
    }

    MSG message{};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
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
        g_ready_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        if (!g_ready_event) {
            g_callback = nullptr;
            return FALSE;
        }
        g_timer = CreateThreadpoolTimer(timer_callback, nullptr, nullptr);
        if (!g_timer) {
            CloseHandle(g_ready_event);
            g_ready_event = nullptr;
            g_callback = nullptr;
            return FALSE;
        }
        ready_event = g_ready_event;
        g_running = true;
        try {
            g_thread = std::thread(event_thread);
        } catch (...) {
            g_running = false;
            CloseThreadpoolTimer(g_timer);
            g_timer = nullptr;
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
    PTP_TIMER timer_to_close = nullptr;
    HANDLE promoted_process = nullptr;
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        if (!g_running && !g_thread.joinable()) {
            return TRUE;
        }
        g_running = false;
        cancel_timer_locked();
        if (g_thread_id) {
            PostThreadMessageW(g_thread_id, WM_QUIT, 0, 0);
        }
        event_thread_to_join = std::move(g_thread);
        timer_to_close = g_timer;
        g_timer = nullptr;
        promoted_process = g_promoted_process;
        g_promoted_process = nullptr;
    }
    if (event_thread_to_join.joinable()) {
        event_thread_to_join.join();
    }
    if (timer_to_close) {
        WaitForThreadpoolTimerCallbacks(timer_to_close, TRUE);
        CloseThreadpoolTimer(timer_to_close);
    }
    if (promoted_process) {
        SetPriorityClass(promoted_process, NORMAL_PRIORITY_CLASS);
        CloseHandle(promoted_process);
    }
    std::lock_guard<std::mutex> lock(g_mutex);
    g_target_process_id = 0;
    g_callback = nullptr;
    return TRUE;
}

BOOL WINAPI optimizer_is_running() {
    std::lock_guard<std::mutex> lock(g_mutex);
    return g_running ? TRUE : FALSE;
}
