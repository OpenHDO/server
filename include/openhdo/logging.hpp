#pragma once

#include <chrono>
#include <functional>
#include <initializer_list>
#include <mutex>
#include <optional>
#include <ostream>
#include <string>
#include <string_view>

namespace openhdo {

enum class LogLevel {
    trace,
    debug,
    info,
    warn,
    error,
};

[[nodiscard]] std::optional<LogLevel> parse_log_level(std::string_view value) noexcept;
[[nodiscard]] std::string_view log_level_name(LogLevel level) noexcept;

struct LogField {
    std::string key;
    std::string value;
};

class Logger {
public:
    using Clock = std::chrono::system_clock;
    using ClockSource = std::function<Clock::time_point()>;

    explicit Logger(std::ostream& output, LogLevel minimum = LogLevel::info,
                    ClockSource clock = {});

    void log(LogLevel level, std::string_view component, std::string_view event,
             std::initializer_list<LogField> fields = {});

    void trace(std::string_view component, std::string_view event,
               std::initializer_list<LogField> fields = {});
    void debug(std::string_view component, std::string_view event,
               std::initializer_list<LogField> fields = {});
    void info(std::string_view component, std::string_view event,
              std::initializer_list<LogField> fields = {});
    void warn(std::string_view component, std::string_view event,
              std::initializer_list<LogField> fields = {});
    void error(std::string_view component, std::string_view event,
               std::initializer_list<LogField> fields = {});

private:
    std::ostream& output_;
    LogLevel minimum_;
    ClockSource clock_;
    mutable std::mutex mutex_;
};

}  // namespace openhdo
