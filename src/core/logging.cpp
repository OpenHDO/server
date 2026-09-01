#include <openhdo/logging.hpp>

#include <chrono>
#include <ctime>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <utility>

namespace openhdo {
namespace {

[[nodiscard]] bool at_least(const LogLevel value, const LogLevel minimum) noexcept {
    return static_cast<int>(value) >= static_cast<int>(minimum);
}

[[nodiscard]] std::string json_escape(const std::string_view value) {
    std::ostringstream escaped;
    for (const char character : value) {
        switch (character) {
            case '"':
                escaped << "\\\"";
                break;
            case '\\':
                escaped << "\\\\";
                break;
            case '\b':
                escaped << "\\b";
                break;
            case '\f':
                escaped << "\\f";
                break;
            case '\n':
                escaped << "\\n";
                break;
            case '\r':
                escaped << "\\r";
                break;
            case '\t':
                escaped << "\\t";
                break;
            default:
                if (static_cast<unsigned char>(character) < 0x20U) {
                    escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                            << static_cast<unsigned int>(static_cast<unsigned char>(character));
                } else {
                    escaped << character;
                }
        }
    }
    return escaped.str();
}

[[nodiscard]] std::string timestamp(const Logger::Clock::time_point value) {
    const auto milliseconds_since_epoch =
        std::chrono::duration_cast<std::chrono::milliseconds>(value.time_since_epoch());
    const auto seconds_since_epoch =
        std::chrono::duration_cast<std::chrono::seconds>(milliseconds_since_epoch);
    const auto milliseconds =
        (milliseconds_since_epoch - std::chrono::duration_cast<std::chrono::milliseconds>(
                                      seconds_since_epoch))
            .count();
    const auto time = Logger::Clock::to_time_t(Logger::Clock::time_point{seconds_since_epoch});

    std::tm utc{};
#if defined(_WIN32)
    gmtime_s(&utc, &time);
#else
    gmtime_r(&time, &utc);
#endif

    std::ostringstream result;
    result << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S") << '.' << std::setfill('0')
           << std::setw(3) << milliseconds << 'Z';
    return result.str();
}

}  // namespace

std::optional<LogLevel> parse_log_level(const std::string_view value) noexcept {
    if (value == "trace") {
        return LogLevel::trace;
    }
    if (value == "debug") {
        return LogLevel::debug;
    }
    if (value == "info") {
        return LogLevel::info;
    }
    if (value == "warn") {
        return LogLevel::warn;
    }
    if (value == "error") {
        return LogLevel::error;
    }
    return std::nullopt;
}

std::string_view log_level_name(const LogLevel level) noexcept {
    switch (level) {
        case LogLevel::trace:
            return "trace";
        case LogLevel::debug:
            return "debug";
        case LogLevel::info:
            return "info";
        case LogLevel::warn:
            return "warn";
        case LogLevel::error:
            return "error";
    }
    return "unknown";
}

Logger::Logger(std::ostream& output, const LogLevel minimum, ClockSource clock)
    : output_(output), minimum_(minimum), clock_(std::move(clock)) {
    if (!clock_) {
        clock_ = [] { return Clock::now(); };
    }
}

void Logger::log(const LogLevel level, const std::string_view component,
                 const std::string_view event, const std::initializer_list<LogField> fields) {
    if (!at_least(level, minimum_)) {
        return;
    }

    const std::lock_guard lock(mutex_);
    output_ << "{\"ts\":\"" << json_escape(timestamp(clock_())) << "\",\"level\":\""
            << log_level_name(level) << "\",\"component\":\"" << json_escape(component)
            << "\",\"event\":\"" << json_escape(event) << "\",\"fields\":{";

    bool first = true;
    for (const auto& field : fields) {
        if (!first) {
            output_ << ',';
        }
        first = false;
        output_ << '"' << json_escape(field.key) << "\":\"" << json_escape(field.value)
                << '"';
    }
    output_ << "}}\n";
}

void Logger::trace(const std::string_view component, const std::string_view event,
                   const std::initializer_list<LogField> fields) {
    log(LogLevel::trace, component, event, fields);
}

void Logger::debug(const std::string_view component, const std::string_view event,
                   const std::initializer_list<LogField> fields) {
    log(LogLevel::debug, component, event, fields);
}

void Logger::info(const std::string_view component, const std::string_view event,
                  const std::initializer_list<LogField> fields) {
    log(LogLevel::info, component, event, fields);
}

void Logger::warn(const std::string_view component, const std::string_view event,
                  const std::initializer_list<LogField> fields) {
    log(LogLevel::warn, component, event, fields);
}

void Logger::error(const std::string_view component, const std::string_view event,
                   const std::initializer_list<LogField> fields) {
    log(LogLevel::error, component, event, fields);
}

}  // namespace openhdo
