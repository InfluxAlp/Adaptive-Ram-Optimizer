#pragma once

#include <stdint.h>
#include <windows.h>

#ifdef OPTIMIZER_CORE_EXPORTS
#define OPTIMIZER_CORE_API __declspec(dllexport)
#else
#define OPTIMIZER_CORE_API __declspec(dllimport)
#endif

struct TelemetryData {
    DWORD process_id;
    wchar_t process_name[256];
    wchar_t window_title[512];
    uint64_t timestamp;
    uint64_t previous_focus_duration_ms;
};

typedef void (*TelemetryCallback)(TelemetryData data);

extern "C" {
OPTIMIZER_CORE_API BOOL WINAPI optimizer_start(TelemetryCallback callback);
OPTIMIZER_CORE_API BOOL WINAPI optimizer_stop();
OPTIMIZER_CORE_API BOOL WINAPI optimizer_is_running();
}
